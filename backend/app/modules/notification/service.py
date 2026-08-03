from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import Principal
from app.core.exceptions import ResourceNotFoundError, ServiceConfigurationError
from app.db.base import new_ulid
from app.integrations.feishu.service import FeishuService
from app.models.notification.notification import Notification
from app.models.system.outbox_event import OutboxEvent
from app.modules.notification.repository import NotificationRepository
from app.modules.notification.schemas import NotificationSendRequest, NotificationSendResponse


class NotificationService:
    def __init__(
        self,
        session: AsyncSession | None,
        repository: NotificationRepository | None,
        feishu: FeishuService | None = None,
    ) -> None:
        self.session = session
        self.repository = repository
        self.feishu = feishu

    async def notify_sales(
        self,
        receiver_open_id: str,
        content: str,
        *,
        customer_id: str | None = None,
        user_id: str | None = None,
    ) -> bool:
        """Dispatch a sales alert through the first enabled channel.

        Feishu is the first implementation. Email and SMS adapters can be
        added here without changing lead scoring orchestration.
        """
        if self.feishu is None or not self.feishu.configured:
            return False
        await self.feishu.send_text_message(
            receiver_open_id,
            content,
            customer_id=customer_id,
            user_id=user_id,
        )
        return True

    async def send(
        self,
        principal: Principal,
        payload: NotificationSendRequest,
    ) -> NotificationSendResponse:
        if self.session is None or self.repository is None:
            raise ServiceConfigurationError(
                "Persistent notification delivery is not configured."
            )
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
