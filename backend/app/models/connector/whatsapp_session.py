from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import (
    BIGINT_UNSIGNED,
    Base,
    BigIntPrimaryKeyMixin,
    TimestampMixin,
)
from app.db.types import UTCDateTime


class WhatsAppSession(BigIntPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "whatsapp_sessions"
    __table_args__ = (
        UniqueConstraint(
            "connector_id",
            name="uq_whatsapp_sessions_connector",
        ),
        UniqueConstraint(
            "session_id",
            name="uq_whatsapp_sessions_openwa_session",
        ),
        UniqueConstraint(
            "session_name",
            name="uq_whatsapp_sessions_session_name",
        ),
        CheckConstraint(
            "status IN "
            "('created','starting','waiting_qr','connected','disconnected','error')",
            name="status_allowed",
        ),
        ForeignKeyConstraint(
            ["connector_id", "tenant_id"],
            ["connectors.id", "connectors.tenant_id"],
            ondelete="CASCADE",
            name="fk_whatsapp_sessions_connector_tenant",
        ),
        Index("ix_whatsapp_sessions_tenant_status", "tenant_id", "status"),
        Index("ix_whatsapp_sessions_tenant_connector", "tenant_id", "connector_id"),
    )

    tenant_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    connector_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED,
        nullable=False,
    )
    session_id: Mapped[str | None] = mapped_column(String(64))
    session_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="created",
        server_default="created",
    )
    qr_code: Mapped[str | None] = mapped_column(mysql.MEDIUMTEXT())
    last_connected_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_error: Mapped[str | None] = mapped_column(Text())
    session_data: Mapped[dict[str, object] | None] = mapped_column(JSON)

    tenant = relationship("Tenant", lazy="raise", overlaps="connector,whatsapp_session")
    connector = relationship(
        "Connector",
        back_populates="whatsapp_session",
        lazy="raise",
        overlaps="tenant",
    )
