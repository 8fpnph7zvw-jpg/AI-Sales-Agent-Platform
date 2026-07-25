from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import (
    BIGINT_UNSIGNED,
    Base,
    BigIntPrimaryKeyMixin,
    PublicIdMixin,
    SoftDeleteMixin,
    TimestampMixin,
)


class Product(
    BigIntPrimaryKeyMixin,
    PublicIdMixin,
    TimestampMixin,
    SoftDeleteMixin,
    Base,
):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("tenant_id", "sku", name="tenant_sku"),)

    tenant_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    sku: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(120))
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    currency: Mapped[str] = mapped_column(mysql.CHAR(3), nullable=False)
    base_price: Mapped[Decimal] = mapped_column(mysql.DECIMAL(19, 4), nullable=False)
    min_order_qty: Mapped[Decimal | None] = mapped_column(mysql.DECIMAL(19, 4))
    attributes: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="active", server_default="active"
    )
