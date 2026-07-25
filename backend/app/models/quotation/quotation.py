from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    ForeignKey,
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
    PublicIdMixin,
    TimestampMixin,
    VersionMixin,
)
from app.db.types import UTCDateTime


class Quotation(
    BigIntPrimaryKeyMixin,
    PublicIdMixin,
    TimestampMixin,
    VersionMixin,
    Base,
):
    __tablename__ = "quotations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "quotation_no", name="tenant_number"),
        CheckConstraint(
            "status IN ('draft','pending_approval','approved','sent','accepted',"
            "'rejected','expired','cancelled')",
            name="status_allowed",
        ),
        Index("ix_quotations_tenant_status_created", "tenant_id", "status", "created_at"),
        Index("ix_quotations_customer", "customer_id", "created_at"),
    )

    tenant_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    quotation_no: Mapped[str] = mapped_column(String(64), nullable=False)
    customer_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    conversation_id: Mapped[int | None] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("conversations.id", ondelete="SET NULL"),
    )
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="draft", server_default="draft"
    )
    currency: Mapped[str] = mapped_column(mysql.CHAR(3), nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(
        mysql.DECIMAL(19, 4), nullable=False, default=0, server_default="0"
    )
    discount_amount: Mapped[Decimal] = mapped_column(
        mysql.DECIMAL(19, 4), nullable=False, default=0, server_default="0"
    )
    tax_amount: Mapped[Decimal] = mapped_column(
        mysql.DECIMAL(19, 4), nullable=False, default=0, server_default="0"
    )
    shipping_amount: Mapped[Decimal] = mapped_column(
        mysql.DECIMAL(19, 4), nullable=False, default=0, server_default="0"
    )
    total_amount: Mapped[Decimal] = mapped_column(
        mysql.DECIMAL(19, 4), nullable=False, default=0, server_default="0"
    )
    valid_until: Mapped[date | None] = mapped_column(Date)
    incoterm: Mapped[str | None] = mapped_column(String(16))
    payment_terms: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text)
    ai_suggestion: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_by: Mapped[int | None] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    approved_by: Mapped[int | None] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    customer = relationship("Customer", lazy="raise")
    conversation = relationship("Conversation", lazy="raise")
    items = relationship(
        "QuotationItem",
        back_populates="quotation",
        cascade="all, delete-orphan",
        lazy="raise",
    )
