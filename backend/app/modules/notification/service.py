from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import Principal
from app.core.exceptions import ResourceNotFoundError
from app.db.base import new_ulid
from app.models.notification.notification import Notification
from app.models.system.outbox_event import OutboxEvent
from app.modules.notification.repository import NotificationRepository
from app.modules.notification.schemas import NotificationSendRequest, NotificationSendResponse


class NotificationService:
    def __init__(
        self,
        session: AsyncSession,
        repository: NotificationRepository,
    ) -> None:
        self.session = session
        self.repository = repository

    async def send(
        self,
        principal: Principal,
        payload: NotificationSendRequest,
    ) -> NotificationSendResponse:
        if payload.dedupe_key:
            existing = await self.repository.get_by_dedupe_key(
                principal.tenant_id,
                payload.dedupe_key,
            )
            if existing is not None:
                return NotificationSendResponse(
                    id=existing.public_id,
                    status=existing.status,
                    channel=existing.channel,
                    duplicate=True,
                )

        user = None
        if payload.user_id:
            user = await self.repository.get_user(
                principal.tenant_id,
                payload.user_id,
            )
            if user is None:
                raise ResourceNotFoundError("Notification recipient")

        now = datetime.now(UTC)
        notification = Notification(
            tenant_id=principal.tenant_id,
            user_id=user.id if user else None,
            type=payload.type,
            channel=payload.channel,
            title=payload.title,
            content=payload.content,
            resource_type=payload.resource_type,
            resource_public_id=payload.resource_id,
            priority=payload.priority,
            status="pending",
            dedupe_key=payload.dedupe_key or f"notification:{new_ulid()}",
            created_at=now,
        )
        self.repository.add(notification)
        await self.session.flush()
        self.session.add(
            OutboxEvent(
                tenant_id=principal.tenant_id,
                aggregate_type="notification",
                aggregate_id=notification.public_id,
                event_type="notification.requested.v1",
                payload={
                    "notification_id": notification.public_id,
                    "channel": notification.channel,
                },
                available_at=now,
            )
        )
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            if payload.dedupe_key:
                existing = await self.repository.get_by_dedupe_key(
                    principal.tenant_id,
                    payload.dedupe_key,
                )
                if existing is not None:
                    return NotificationSendResponse(
                        id=existing.public_id,
                        status=existing.status,
                        channel=existing.channel,
                        duplicate=True,
                    )
            raise
        return NotificationSendResponse(
            id=notification.public_id,
            status=notification.status,
            channel=notification.channel,
        )
