from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import (
    BIGINT_UNSIGNED,
    Base,
    BigIntPrimaryKeyMixin,
    PublicIdMixin,
    utc_now,
)
from app.db.types import UTCDateTime


class OutboxEvent(BigIntPrimaryKeyMixin, PublicIdMixin, Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        Index("ix_outbox_events_dispatch", "status", "available_at", "id"),
        Index("ix_outbox_events_aggregate", "tenant_id", "aggregate_type", "aggregate_id"),
    )

    tenant_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    aggregate_type: Mapped[str] = mapped_column(String(80), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(160), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="pending", server_default="pending"
    )
    attempt_count: Mapped[int] = mapped_column(
        mysql.INTEGER(unsigned=True), nullable=False, default=0, server_default="0"
    )
    available_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)
    locked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    locked_by: Mapped[str | None] = mapped_column(String(120))
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
        server_default=func.current_timestamp(),
    )
