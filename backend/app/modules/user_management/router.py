from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import Principal, get_current_principal, require_any_permission
from app.core.config import get_settings
from app.core.security import SecurityManager
from app.db.session import get_db
from app.modules.user_management.repository import UserManagementRepository
from app.modules.user_management.schemas import (
    SalesUserCreate,
    SalesUserListResponse,
    SalesUserRead,
    SalesUserUpdate,
    UserFeishuStatusResponse,
)
from app.modules.user_management.service import UserManagementService

router = APIRouter(prefix="/users", tags=["User Management"])


def get_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> UserManagementService:
    return UserManagementService(
        session,
        UserManagementRepository(session),
        SecurityManager(get_settings()),
    )


@router.get("", response_model=SalesUserListResponse)
async def list_users(
    service: Annotated[UserManagementService, Depends(get_service)],
    principal: Annotated[Principal, Depends(require_any_permission("user.read"))],
) -> SalesUserListResponse:
    return await service.list(principal)


@router.post("", response_model=SalesUserRead, status_code=status.HTTP_201_CREATED)
async def create_sales_user(
    payload: SalesUserCreate,
    service: Annotated[UserManagementService, Depends(get_service)],
    principal: Annotated[
        Principal,
        Depends(require_any_permission("user.manage", "user.invite")),
    ],
) -> SalesUserRead:
    return await service.create(principal, payload)


@router.patch("/{user_id}", response_model=SalesUserRead)
async def update_sales_user(
    user_id: str,
    payload: SalesUserUpdate,
    service: Annotated[UserManagementService, Depends(get_service)],
    principal: Annotated[Principal, Depends(require_any_permission("user.manage"))],
) -> SalesUserRead:
    return await service.update(principal, user_id, payload)


@router.get("/{user_id}/feishu/status", response_model=UserFeishuStatusResponse)
async def get_user_feishu_status(
    user_id: str,
    service: Annotated[UserManagementService, Depends(get_service)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> UserFeishuStatusResponse:
    return await service.feishu_status(principal, user_id)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sales_user(
    user_id: str,
    service: Annotated[UserManagementService, Depends(get_service)],
    principal: Annotated[Principal, Depends(require_any_permission("user.manage"))],
) -> Response:
    await service.delete(principal, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
