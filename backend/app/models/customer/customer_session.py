from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import (
    BIGINT_UNSIGNED,
    Base,
    BigIntPrimaryKeyMixin,
    PublicIdMixin,
    TimestampMixin,
)
from app.db.types import UTCDateTime


class CustomerSession(BigIntPrimaryKeyMixin, PublicIdMixin, TimestampMixin, Base):
    __tablename__ = "customer_sessions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "connector_id",
            "external_contact_id",
            "external_thread_id",
            name="external_identity",
        ),
        Index("ix_customer_sessions_customer_last_seen", "customer_id", "last_seen_at"),
    )

    tenant_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    customer_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
    )
    connector_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("connectors.id", ondelete="RESTRICT"),
        nullable=False,
    )
    external_contact_id: Mapped[str] = mapped_column(String(255), nullable=False)
    external_thread_id: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", server_default=""
    )
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="active", server_default="active"
    )
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )

    customer = relationship("Customer", back_populates="sessions")
    connector = relationship("Connector", lazy="raise")
    conversations = relationship("Conversation", back_populates="customer_session", lazy="raise")
