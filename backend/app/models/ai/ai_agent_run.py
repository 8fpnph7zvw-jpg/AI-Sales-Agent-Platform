from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import (
    BIGINT_UNSIGNED,
    Base,
    BigIntPrimaryKeyMixin,
    PublicIdMixin,
    TimestampMixin,
)
from app.db.types import UTCDateTime


class AiAgentRun(BigIntPrimaryKeyMixin, PublicIdMixin, TimestampMixin, Base):
    __tablename__ = "ai_agent_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','succeeded','failed','cancelled','timed_out')",
            name="status_allowed",
        ),
        Index("ix_ai_agent_runs_conversation_created", "conversation_id", "created_at"),
        Index("ix_ai_agent_runs_tenant_status", "tenant_id", "status", "created_at"),
        Index("ix_ai_agent_runs_dify_task", "dify_task_id"),
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
    trigger_message_id: Mapped[int | None] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("messages.id", ondelete="SET NULL"),
    )
    output_message_id: Mapped[int | None] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("messages.id", ondelete="SET NULL"),
    )
    prompt_id: Mapped[int | None] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("prompts.id", ondelete="SET NULL"),
    )
    run_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="queued", server_default="queued"
    )
    model_name: Mapped[str | None] = mapped_column(String(120))
    dify_conversation_id: Mapped[str | None] = mapped_column(String(128))
    dify_task_id: Mapped[str | None] = mapped_column(String(128))
    input_redacted: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    output_redacted: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    extracted_needs: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    citations: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    policy_result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    intent_score: Mapped[Decimal | None] = mapped_column(mysql.DECIMAL(5, 2))
    prompt_tokens: Mapped[int | None] = mapped_column(mysql.INTEGER(unsigned=True))
    completion_tokens: Mapped[int | None] = mapped_column(mysql.INTEGER(unsigned=True))
    cost_amount: Mapped[Decimal | None] = mapped_column(mysql.DECIMAL(19, 6))
    cost_currency: Mapped[str | None] = mapped_column(mysql.CHAR(3))
    latency_ms: Mapped[int | None] = mapped_column(mysql.INTEGER(unsigned=True))
    error_code: Mapped[str | None] = mapped_column(String(120))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    conversation = relationship("Conversation", lazy="raise")
    trigger_message = relationship("Message", foreign_keys=[trigger_message_id], lazy="raise")
    output_message = relationship("Message", foreign_keys=[output_message_id], lazy="raise")
    prompt = relationship("Prompt", lazy="raise")
