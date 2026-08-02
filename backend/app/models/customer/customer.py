from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Boolean, CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy.dialects import mysql
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


class Customer(
    BigIntPrimaryKeyMixin,
    PublicIdMixin,
    TimestampMixin,
    SoftDeleteMixin,
    Base,
):
    __tablename__ = "customers"
    __table_args__ = (
        CheckConstraint(
            "intent_score IS NULL OR (intent_score >= 0 AND intent_score <= 100)",
            name="intent_score_range",
        ),
        Index("ix_customers_tenant_owner_stage", "tenant_id", "owner_user_id", "lifecycle_stage"),
        Index("ix_customers_tenant_score", "tenant_id", "intent_score"),
        Index("ix_customers_tenant_email", "tenant_id", "email"),
        Index("ix_customers_tenant_phone", "tenant_id", "phone_e164"),
    )

    tenant_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    company_name: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(254))
    phone_e164: Mapped[str | None] = mapped_column(String(32))
    country_code: Mapped[str | None] = mapped_column(mysql.CHAR(2))
    language: Mapped[str | None] = mapped_column(String(16))
    lifecycle_stage: Mapped[str] = mapped_column(
        String(32), nullable=False, default="new", server_default="new"
    )
    intent_score: Mapped[Decimal | None] = mapped_column(mysql.DECIMAL(5, 2))
    intent_level: Mapped[str | None] = mapped_column(String(24))
    score_explanation: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    source_type: Mapped[str | None] = mapped_column(String(64))
    source_ref: Mapped[str | None] = mapped_column(String(255))
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    owner_user_id: Mapped[int | None] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    created_by: Mapped[int | None] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    consent_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="unknown", server_default="unknown"
    )
    do_not_contact: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    last_contact_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    notes: Mapped[str | None] = mapped_column(Text)

    tenant = relationship("Tenant", lazy="raise")
    owner = relationship("User", foreign_keys=[owner_user_id], lazy="raise")
    sessions = relationship("CustomerSession", back_populates="customer", lazy="raise")
    conversations = relationship("Conversation", back_populates="customer", lazy="raise")
    scores = relationship(
        "CustomerScore",
        back_populates="customer",
        cascade="all, delete-orphan",
        lazy="raise",
    )
