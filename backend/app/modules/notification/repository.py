from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth.user import User
from app.models.notification.notification import Notification


class NotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_user(self, tenant_id: int, public_id: str) -> User | None:
        statement = select(User).where(
            User.tenant_id == tenant_id,
            User.public_id == public_id,
            User.status == "active",
            User.deleted_at.is_(None),
        )
        return await self.session.scalar(statement)

    async def get_by_dedupe_key(
        self,
        tenant_id: int,
        dedupe_key: str,
    ) -> Notification | None:
        statement = select(Notification).where(
            Notification.tenant_id == tenant_id,
            Notification.dedupe_key == dedupe_key,
        )
        return await self.session.scalar(statement)

    def add(self, notification: Notification) -> None:
        self.session.add(notification)
