from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import httpx
from pydantic import ValidationError

from app.core.config import Settings
from app.integrations.feishu.exceptions import FeishuAPIError, FeishuConfigurationError
from app.integrations.feishu.schemas import (
    FeishuMessageResponse,
    FeishuSendResult,
    FeishuTenantTokenResponse,
)

logger = logging.getLogger(__name__)

TOKEN_REFRESH_SKEW_SECONDS = 60
TOKEN_INVALID_CODES = frozenset({99991663, 99991668, 99991671})


class FeishuClient:
    def __init__(
        self,
        settings: Settings,
        *,
        app_id: str | None = None,
        app_secret: str | None = None,
        enabled: bool | None = None,
    ) -> None:
        self.settings = settings
        self.app_id = settings.feishu_app_id if app_id is None else app_id
        self.app_secret = settings.feishu_app_secret if app_secret is None else app_secret
        self.enabled = settings.feishu_enabled if enabled is None else enabled
        self._tenant_access_token: str | None = None
        self._token_expires_at = 0.0
        self._token_lock = asyncio.Lock()

    @property
    def configured(self) -> bool:
        return bool(
            self.enabled
            and self.app_id
            and self.app_secret
        )

    async def get_tenant_access_token(self, *, force_refresh: bool = False) -> str:
        self._ensure_configured()
        if not force_refresh and self._token_is_valid():
            return self._tenant_access_token or ""

        async with self._token_lock:
            if not force_refresh and self._token_is_valid():
                return self._tenant_access_token or ""
            logger.info("feishu_token_get_started")
            try:
                body = await self._post_json(
                    "open-apis/auth/v3/tenant_access_token/internal",
                    json_body={
                        "app_id": self.app_id,
                        "app_secret": self.app_secret,
                    },
                )
                token_response = FeishuTenantTokenResponse.model_validate(body)
                if token_response.code != 0 or not token_response.tenant_access_token:
                    raise FeishuAPIError(
                        token_response.msg or "tenant access token request was rejected",
                        error_code="FEISHU_TOKEN_REQUEST_FAILED",
                    )
            except ValidationError as exc:
                logger.exception("feishu_token_get_failed")
                raise FeishuAPIError(
                    "tenant access token response was invalid",
                    error_code="FEISHU_TOKEN_RESPONSE_INVALID",
                ) from exc
            except Exception:
                logger.exception("feishu_token_get_failed")
                raise
            lifetime = max(token_response.expire - TOKEN_REFRESH_SKEW_SECONDS, 1)
            self._tenant_access_token = token_response.tenant_access_token
            self._token_expires_at = time.monotonic() + lifetime
            logger.info("feishu_token_get_success expires_in=%s", token_response.expire)
            return token_response.tenant_access_token

    async def send_text_message(
        self,
        receiver_open_id: str,
        content: str,
    ) -> FeishuSendResult:
        token = await self.get_tenant_access_token()
        body = await self._send_text_request(receiver_open_id, content, token)
        if int(body.get("code", -1)) in TOKEN_INVALID_CODES:
            token = await self.get_tenant_access_token(force_refresh=True)
            body = await self._send_text_request(receiver_open_id, content, token)
        try:
            message_response = FeishuMessageResponse.model_validate(body)
        except ValidationError as exc:
            raise FeishuAPIError(
                "message response was invalid",
                error_code="FEISHU_MESSAGE_RESPONSE_INVALID",
            ) from exc
        if message_response.code != 0:
            raise FeishuAPIError(
                message_response.msg or "message request was rejected",
                error_code="FEISHU_MESSAGE_SEND_FAILED",
            )
        return FeishuSendResult(
            message_id=(message_response.data.message_id if message_response.data else None)
        )

    async def _send_text_request(
        self,
        receiver_open_id: str,
        content: str,
        token: str,
    ) -> dict[str, Any]:
        return await self._post_json(
            "open-apis/im/v1/messages",
            params={"receive_id_type": "open_id"},
            headers={"Authorization": f"Bearer {token}"},
            json_body={
                "receive_id": receiver_open_id,
                "msg_type": "text",
                "content": json.dumps({"text": content}, ensure_ascii=False),
            },
        )

    async def _post_json(
        self,
        path: str,
        *,
        json_body: dict[str, Any],
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(
                base_url=self.settings.feishu_api_base_url.rstrip("/") + "/",
                timeout=self.settings.feishu_timeout_seconds,
            ) as client:
                response = await client.post(
                    path,
                    params=params,
                    headers=headers,
                    json=json_body,
                )
                response.raise_for_status()
                body = response.json()
        except httpx.HTTPStatusError as exc:
            raise FeishuAPIError(
                "API returned an HTTP error",
                upstream_status_code=exc.response.status_code,
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise FeishuAPIError("API request failed") from exc
        if not isinstance(body, dict):
            raise FeishuAPIError(
                "API response was not a JSON object",
                error_code="FEISHU_RESPONSE_INVALID",
            )
        return body

    def _token_is_valid(self) -> bool:
        return bool(
            self._tenant_access_token and time.monotonic() < self._token_expires_at
        )

    def _ensure_configured(self) -> None:
        if not self.configured:
            raise FeishuConfigurationError()
