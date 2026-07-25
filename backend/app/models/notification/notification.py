from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import (
    BIGINT_UNSIGNED,
    Base,
    BigIntPrimaryKeyMixin,
    PublicIdMixin,
    utc_now,
)
from app.db.types import UTCDateTime


class Notification(BigIntPrimaryKeyMixin, PublicIdMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("tenant_id", "dedupe_key", name="tenant_dedupe"),
        Index("ix_notifications_user_unread", "user_id", "read_at", "created_at"),
        Index("ix_notifications_tenant_status", "tenant_id", "status", "created_at"),
    )

    tenant_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int | None] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("users.id", ondelete="CASCADE"),
    )
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(80))
    resource_public_id: Mapped[str | None] = mapped_column(mysql.CHAR(26))
    priority: Mapped[str] = mapped_column(
        String(16), nullable=False, default="normal", server_default="normal"
    )
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="pending", server_default="pending"
    )
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(120))
    read_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    failed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
        server_default=func.current_timestamp(),
    )

    user = relationship("User", lazy="raise")
