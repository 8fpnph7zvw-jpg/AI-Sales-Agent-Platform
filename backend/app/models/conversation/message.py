from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, String, UniqueConstraint, func
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


class Message(BigIntPrimaryKeyMixin, PublicIdMixin, Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("conversation_id", "sequence_no", name="conversation_sequence"),
        UniqueConstraint("tenant_id", "idempotency_key", name="tenant_idempotency"),
        CheckConstraint(
            "direction IN ('inbound','outbound','internal')",
            name="direction_allowed",
        ),
        CheckConstraint(
            "sender_type IN ('customer','ai','user','system')",
            name="sender_type_allowed",
        ),
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
        Index("ix_messages_external", "connector_id", "external_message_id"),
        Index("ix_messages_tenant_status", "tenant_id", "status", "created_at"),
    )

    tenant_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    conversation_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    connector_id: Mapped[int | None] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("connectors.id", ondelete="SET NULL"),
    )
    sequence_no: Mapped[int] = mapped_column(mysql.INTEGER(unsigned=True), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    sender_type: Mapped[str] = mapped_column(String(16), nullable=False)
    sender_ref: Mapped[str | None] = mapped_column(String(255))
    message_type: Mapped[str] = mapped_column(String(32), nullable=False)
    content_text: Mapped[str | None] = mapped_column(mysql.MEDIUMTEXT)
    content_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    reply_to_message_id: Mapped[int | None] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("messages.id", ondelete="SET NULL"),
    )
    external_message_id: Mapped[str | None] = mapped_column(String(255))
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="received", server_default="received"
    )
    prompt_id: Mapped[int | None] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("prompts.id", ondelete="SET NULL"),
    )
    citations: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    token_usage: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(120))
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    delivered_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    read_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
        server_default=func.current_timestamp(),
    )

    conversation = relationship("Conversation", back_populates="messages")
    connector = relationship("Connector", lazy="raise")
    reply_to = relationship("Message", remote_side="Message.id", lazy="raise")
    prompt = relationship("Prompt", lazy="raise")
