from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import Principal, require_any_permission
from app.connectors.feishu.repository import FeishuConnectorRepository
from app.connectors.feishu.service import FeishuConnectorService
from app.core.config import get_settings
from app.core.encryption import ConfigCipher
from app.db.session import get_db
from app.integrations.feishu.schemas import FeishuConfigStatusResponse, FeishuTestResponse

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
