from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, String
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import (
    BIGINT_UNSIGNED,
    Base,
    BigIntPrimaryKeyMixin,
    PublicIdMixin,
    TimestampMixin,
    VersionMixin,
)
from app.db.types import UTCDateTime


class Conversation(
    BigIntPrimaryKeyMixin,
    PublicIdMixin,
    TimestampMixin,
    VersionMixin,
    Base,
):
    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open','pending','closed','blocked')",
            name="status_allowed",
        ),
        CheckConstraint(
            "mode IN ('ai','assisted','human')",
            name="mode_allowed",
        ),
        Index(
            "ix_conversations_tenant_assignee_status",
            "tenant_id",
            "assigned_user_id",
            "status",
        ),
        Index("ix_conversations_tenant_last_message", "tenant_id", "last_message_at"),
        Index("ix_conversations_customer", "customer_id", "created_at"),
    )

    tenant_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    customer_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    customer_session_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("customer_sessions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    subject: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="open", server_default="open"
    )
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="ai", server_default="ai")
    assigned_user_id: Mapped[int | None] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    priority: Mapped[str] = mapped_column(
        String(16), nullable=False, default="normal", server_default="normal"
    )
    unread_count: Mapped[int] = mapped_column(
        mysql.INTEGER(unsigned=True), nullable=False, default=0, server_default="0"
    )
    ai_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    handoff_reason: Mapped[str | None] = mapped_column(String(500))
    last_message_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    customer = relationship("Customer", back_populates="conversations")
    customer_session = relationship("CustomerSession", back_populates="conversations")
    assignee = relationship("User", lazy="raise")
    messages = relationship(
        "Message",
        back_populates="conversation",
        order_by="Message.sequence_no",
        lazy="raise",
    )
