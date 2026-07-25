from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import Principal, require_any_permission
from app.core.config import get_settings
from app.core.encryption import ConfigCipher
from app.db.session import get_db
from app.modules.connector.repository import ConnectorRepository
from app.modules.connector.schemas import (
    ConnectorConfigRequest,
    ConnectorConfigResponse,
    ConnectorListResponse,
    ConnectorRead,
)
from app.modules.connector.service import ConnectorService

router = APIRouter(prefix="/connectors", tags=["Connectors"])


def get_connector_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ConnectorService:
    return ConnectorService(
        session,
        ConnectorRepository(session),
        ConfigCipher(get_settings()),
    )


@router.get("", response_model=ConnectorListResponse)
async def list_connectors(
    service: Annotated[ConnectorService, Depends(get_connector_service)],
    principal: Annotated[
        Principal,
        Depends(require_any_permission("connector.read", "connector.manage")),
    ],
) -> ConnectorListResponse:
    connectors = await service.list(principal)
    return ConnectorListResponse(data=[ConnectorRead.model_validate(item) for item in connectors])


@router.post("/config", response_model=ConnectorConfigResponse)
async def configure_connector(
    payload: ConnectorConfigRequest,
    service: Annotated[ConnectorService, Depends(get_connector_service)],
    principal: Annotated[
        Principal,
        Depends(require_any_permission("connector.secret_manage")),
    ],
) -> ConnectorConfigResponse:
    return await service.configure(principal, payload)
