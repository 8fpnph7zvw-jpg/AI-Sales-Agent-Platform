from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Index, String, Text, UniqueConstraint, func
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


class WebhookLog(BigIntPrimaryKeyMixin, PublicIdMixin, Base):
    __tablename__ = "webhook_logs"
    __table_args__ = (
        UniqueConstraint("connector_id", "provider_event_id", name="connector_event"),
        Index("ix_webhook_logs_dispatch", "status", "next_retry_at", "id"),
        Index("ix_webhook_logs_tenant_received", "tenant_id", "received_at"),
        Index("ix_webhook_logs_trace", "trace_id"),
    )

    tenant_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    connector_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("connectors.id", ondelete="RESTRICT"),
        nullable=False,
    )
    provider_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str | None] = mapped_column(String(120))
    signature_valid: Mapped[bool] = mapped_column(Boolean, nullable=False)
    headers_redacted: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    payload_redacted: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    payload_hash: Mapped[str] = mapped_column(mysql.CHAR(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="received", server_default="received"
    )
    attempt_count: Mapped[int] = mapped_column(
        mysql.INTEGER(unsigned=True), nullable=False, default=0, server_default="0"
    )
    next_retry_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    processed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    error_code: Mapped[str | None] = mapped_column(String(120))
    error_message: Mapped[str | None] = mapped_column(Text)
    trace_id: Mapped[str | None] = mapped_column(String(64))
    received_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
        server_default=func.current_timestamp(),
    )

    connector = relationship("Connector", back_populates="webhook_logs")
