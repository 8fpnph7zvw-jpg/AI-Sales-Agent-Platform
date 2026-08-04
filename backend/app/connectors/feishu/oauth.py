from __future__ import annotations

import base64
import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import Principal
from app.core.config import Settings
from app.core.exceptions import (
    AppError,
    ConflictError,
    PermissionDeniedError,
    ResourceNotFoundError,
    ServiceConfigurationError,
)
from app.integrations.feishu.exceptions import FeishuAPIError
from app.integrations.feishu.schemas import (
    FeishuOAuthTokenResponse,
    FeishuOAuthURLResponse,
    FeishuOAuthUserInfo,
    FeishuOAuthUserInfoResponse,
)
from app.models.connector.feishu_oauth_state import FeishuOAuthState

from .repository import FeishuConnectorRepository
from .service import FeishuConnectorService

logger = logging.getLogger(__name__)

AUTHORIZE_URL = "https://accounts.feishu.cn/open-apis/authen/v1/authorize"
TOKEN_PATH = "open-apis/authen/v2/oauth/token"
USER_INFO_PATH = "open-apis/authen/v1/user_info"


class FeishuOAuthService:
    def __init__(
        self,
        session: AsyncSession,
        repository: FeishuConnectorRepository,
        connector_service: FeishuConnectorService,
        settings: Settings,
    ) -> None:
        self.session = session
        self.repository = repository
        self.connector_service = connector_service
        self.settings = settings

    async def authorization_url(
        self,
        principal: Principal,
        target_user_public_id: str | None,
    ) -> FeishuOAuthURLResponse:
        target_public_id = target_user_public_id or principal.user_public_id
        if (
            target_public_id != principal.user_public_id
            and "user.manage" not in principal.permissions
        ):
            raise PermissionDeniedError("Only administrators can bind another user.")
        user = await self.repository.get_user_by_public_id(
            principal.tenant_id,
            target_public_id,
        )
        if user is None:
            raise ResourceNotFoundError("User")
        credentials = await self.connector_service.get_credentials(principal.tenant_id)
        redirect_uri = self._redirect_uri()
        state = secrets.token_urlsafe(32)
        code_verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode()).digest()
        ).rstrip(b"=").decode()
        now = datetime.now(UTC)
        expires_at = now + timedelta(
            minutes=self.settings.feishu_oauth_state_expire_minutes
        )
        await self.repository.delete_expired_oauth_states(now)
        self.repository.add_oauth_state(
            FeishuOAuthState(
                tenant_id=principal.tenant_id,
                user_id=user.id,
                initiated_by=principal.user_id,
                state_hash=self._state_hash(state),
                code_verifier=code_verifier,
                redirect_uri=redirect_uri,
                expires_at=expires_at,
            )
        )
        await self.session.commit()
        query = urlencode(
            {
                "client_id": credentials.app_id,
                "response_type": "code",
                "redirect_uri": redirect_uri,
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "prompt": "consent",
            }
        )
        return FeishuOAuthURLResponse(
            url=f"{AUTHORIZE_URL}?{query}",
            expires_in=self.settings.feishu_oauth_state_expire_minutes * 60,
        )

    async def handle_callback(
        self,
        *,
        state: str,
        code: str | None,
        error: str | None,
    ) -> str:
        oauth_state = await self.repository.get_oauth_state_for_update(
            self._state_hash(state)
        )
        now = datetime.now(UTC)
        if oauth_state is None:
            raise AppError(400, "FEISHU_OAUTH_STATE_INVALID", "Feishu OAuth state is invalid.")
        if oauth_state.consumed_at is not None:
            raise AppError(400, "FEISHU_OAUTH_STATE_USED", "Feishu OAuth state was already used.")
        if oauth_state.expires_at <= now:
            raise AppError(400, "FEISHU_OAUTH_STATE_EXPIRED", "Feishu OAuth state has expired.")
        oauth_state.consumed_at = now
        if error:
            await self.session.commit()
            logger.info(
                "feishu_oauth_denied tenant_id=%s user_id=%s error=%s",
                oauth_state.tenant_id,
                oauth_state.user_id,
                error,
            )
            return self._frontend_result("denied", error)
        if not code:
            raise AppError(400, "FEISHU_OAUTH_CODE_MISSING", "Feishu OAuth code is missing.")

        user = await self.repository.get_user(oauth_state.tenant_id, oauth_state.user_id)
        if user is None:
            raise ResourceNotFoundError("OAuth target user")
        credentials = await self.connector_service.get_credentials(oauth_state.tenant_id)
        access_token = await self._exchange_code(
            code=code,
            code_verifier=oauth_state.code_verifier,
            redirect_uri=oauth_state.redirect_uri,
            app_id=credentials.app_id,
            app_secret=credentials.app_secret,
        )
        user_info = await self._get_user_info(access_token)
        user.feishu_open_id = user_info.open_id
        user.feishu_name = user_info.name
        user.feishu_bind_status = "bound"
        user.feishu_bind_time = now
        if user_info.mobile:
            user.phone = user_info.mobile
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError(
                "FEISHU_ACCOUNT_ALREADY_BOUND",
                "This Feishu account is already bound to another user.",
            ) from exc
        logger.info(
            "feishu_oauth_bind_success tenant_id=%s user_id=%s",
            oauth_state.tenant_id,
            oauth_state.user_id,
        )
        return self._frontend_result("success", None)

    def error_redirect(self, error_code: str) -> str:
        return self._frontend_result("error", error_code)

    async def _exchange_code(
        self,
        *,
        code: str,
        code_verifier: str,
        redirect_uri: str,
        app_id: str,
        app_secret: str,
    ) -> str:
        body = await self._request_json(
            "POST",
            TOKEN_PATH,
            json={
                "grant_type": "authorization_code",
                "client_id": app_id,
                "client_secret": app_secret,
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
            },
        )
        try:
            response = FeishuOAuthTokenResponse.model_validate(body)
        except ValidationError as exc:
            raise FeishuAPIError(
                "OAuth token response was invalid.",
                error_code="FEISHU_OAUTH_TOKEN_RESPONSE_INVALID",
            ) from exc
        if response.code != 0 or not response.access_token:
            raise FeishuAPIError(
                response.error_description or response.error or "OAuth token request failed.",
                error_code="FEISHU_OAUTH_TOKEN_FAILED",
            )
        return response.access_token

    async def _get_user_info(self, access_token: str) -> FeishuOAuthUserInfo:
        body = await self._request_json(
            "GET",
            USER_INFO_PATH,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        try:
            response = FeishuOAuthUserInfoResponse.model_validate(body)
        except ValidationError as exc:
            raise FeishuAPIError(
                "OAuth user info response was invalid.",
                error_code="FEISHU_OAUTH_USER_INFO_INVALID",
            ) from exc
        if response.code != 0 or response.data is None:
            raise FeishuAPIError(
                response.msg or "OAuth user info request failed.",
                error_code="FEISHU_OAUTH_USER_INFO_FAILED",
            )
        return response.data

    async def _request_json(self, method: str, path: str, **kwargs) -> dict:
        try:
            async with httpx.AsyncClient(
                base_url=self.settings.feishu_api_base_url.rstrip("/") + "/",
                timeout=self.settings.feishu_timeout_seconds,
            ) as client:
                response = await client.request(method, path, **kwargs)
                body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise FeishuAPIError("OAuth API request failed.") from exc
        if not isinstance(body, dict):
            raise FeishuAPIError("OAuth API response was not a JSON object.")
        if response.status_code >= 500:
            raise FeishuAPIError(
                "OAuth API returned a server error.",
                upstream_status_code=response.status_code,
            )
        return body

    def _redirect_uri(self) -> str:
        redirect_uri = self.settings.feishu_oauth_redirect_uri.strip()
        if not redirect_uri:
            raise ServiceConfigurationError("FEISHU_OAUTH_REDIRECT_URI is not configured.")
        return redirect_uri

    def _frontend_result(self, result: str, error: str | None) -> str:
        base_url = self.settings.frontend_base_url.strip().rstrip("/")
        if not base_url:
            raise ServiceConfigurationError("FRONTEND_BASE_URL is not configured.")
        query = {"feishu_oauth": result}
        if error:
            query["error"] = error
        return f"{base_url}/users?{urlencode(query)}"

    @staticmethod
    def _state_hash(state: str) -> str:
        return hashlib.sha256(state.encode()).hexdigest()
