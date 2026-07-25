from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import Principal, require_any_permission
from app.db.session import get_db
from app.modules.notification.repository import NotificationRepository
from app.modules.notification.schemas import NotificationSendRequest, NotificationSendResponse
from app.modules.notification.service import NotificationService

router = APIRouter(prefix="/notifications", tags=["Notifications"])


def get_notification_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> NotificationService:
    return NotificationService(session, NotificationRepository(session))


@router.post(
    "/send",
    response_model=NotificationSendResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def send_notification(
    payload: NotificationSendRequest,
    service: Annotated[NotificationService, Depends(get_notification_service)],
    principal: Annotated[
        Principal,
        Depends(require_any_permission("notification.send")),
    ],
) -> NotificationSendResponse:
    return await service.send(principal, payload)
