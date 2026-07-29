from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import (
    BIGINT_UNSIGNED,
    Base,
    BigIntPrimaryKeyMixin,
    PublicIdMixin,
    SoftDeleteMixin,
    TimestampMixin,
)
from app.db.types import UTCDateTime


class Connector(
    BigIntPrimaryKeyMixin,
    PublicIdMixin,
    TimestampMixin,
    SoftDeleteMixin,
    Base,
):
    __tablename__ = "connectors"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "provider",
            "external_account_id",
            name="tenant_provider_account",
        ),
        UniqueConstraint(
            "session_id",
            name="uq_connectors_openwa_session",
        ),
        UniqueConstraint(
            "id",
            "tenant_id",
            name="uq_connectors_id_tenant",
        ),
        CheckConstraint(
            "status IN ('draft','active','disabled','error')",
            name="status_allowed",
        ),
        Index("ix_connectors_tenant_status", "tenant_id", "status"),
        Index("ix_connectors_tenant_provider", "tenant_id", "provider"),
    )

    tenant_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="draft", server_default="draft"
    )
    session_id: Mapped[str | None] = mapped_column(String(64))
    phone: Mapped[str | None] = mapped_column(String(32))
    last_connected_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_disconnect_reason: Mapped[str | None] = mapped_column(Text)
    capabilities: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    external_account_id: Mapped[str] = mapped_column(String(255), nullable=False)
    health_status: Mapped[str | None] = mapped_column(String(32))
    health_detail: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    last_health_check_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_by: Mapped[int | None] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("users.id", ondelete="SET NULL"),
    )

    tenant = relationship("Tenant", lazy="raise")
    configs = relationship(
        "ConnectorConfig",
        back_populates="connector",
        cascade="all, delete-orphan",
        lazy="raise",
    )
    webhook_logs = relationship("WebhookLog", back_populates="connector", lazy="raise")
    whatsapp_session = relationship(
        "WhatsAppSession",
        back_populates="connector",
        cascade="all, delete-orphan",
        uselist=False,
        lazy="raise",
        overlaps="tenant",
    )
