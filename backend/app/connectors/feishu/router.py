from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import (
    Principal,
    get_current_principal,
    require_any_permission,
)
from app.connectors.feishu.oauth import FeishuOAuthService
from app.connectors.feishu.repository import FeishuConnectorRepository
from app.connectors.feishu.service import FeishuConnectorService
from app.core.config import get_settings
from app.core.encryption import ConfigCipher
from app.core.exceptions import AppError
from app.db.session import get_db
from app.integrations.feishu.schemas import (
    FeishuConfigStatusResponse,
    FeishuOAuthURLResponse,
    FeishuTestResponse,
)

router = APIRouter(prefix="/connectors/feishu", tags=["Feishu Connector"])


def get_feishu_connector_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FeishuConnectorService:
    settings = get_settings()
    return FeishuConnectorService(
        session,
        FeishuConnectorRepository(session),
        ConfigCipher(settings),
        settings,
    )


def get_feishu_oauth_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FeishuOAuthService:
    settings = get_settings()
    repository = FeishuConnectorRepository(session)
    return FeishuOAuthService(
        session,
        repository,
        FeishuConnectorService(
            session,
            repository,
            ConfigCipher(settings),
            settings,
        ),
        settings,
    )


@router.get("/oauth/url", response_model=FeishuOAuthURLResponse)
async def get_feishu_oauth_url(
    service: Annotated[FeishuOAuthService, Depends(get_feishu_oauth_service)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    user_id: Annotated[str | None, Query(min_length=26, max_length=26)] = None,
) -> FeishuOAuthURLResponse:
    return await service.authorization_url(principal, user_id)


@router.get("/oauth/callback", response_class=RedirectResponse)
async def feishu_oauth_callback(
    service: Annotated[FeishuOAuthService, Depends(get_feishu_oauth_service)],
    state_value: Annotated[str, Query(alias="state", min_length=16, max_length=256)],
    code: Annotated[str | None, Query(max_length=4096)] = None,
    error: Annotated[str | None, Query(max_length=120)] = None,
) -> RedirectResponse:
    try:
        redirect_url = await service.handle_callback(
            state=state_value,
            code=code,
            error=error,
        )
    except AppError as exc:
        redirect_url = service.error_redirect(exc.code)
    return RedirectResponse(redirect_url, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{connector_id}/config-status", response_model=FeishuConfigStatusResponse)
async def get_feishu_config_status(
    connector_id: str,
    service: Annotated[FeishuConnectorService, Depends(get_feishu_connector_service)],
    principal: Annotated[
        Principal,
        Depends(require_any_permission("connector.read", "connector.manage")),
    ],
) -> FeishuConfigStatusResponse:
    return FeishuConfigStatusResponse(
        **await service.config_status(principal, connector_id)
    )


@router.post("/test", response_model=FeishuTestResponse)
async def test_feishu_connector(
    service: Annotated[FeishuConnectorService, Depends(get_feishu_connector_service)],
    principal: Annotated[
        Principal,
        Depends(require_any_permission("connector.manage", "connector.secret_manage")),
    ],
) -> FeishuTestResponse:
    result = await service.test_notification(principal)
    return FeishuTestResponse(success=True, message_id=result.message_id)
