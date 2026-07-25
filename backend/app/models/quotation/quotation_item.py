from __future__ import annotations

from decimal import Decimal

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BIGINT_UNSIGNED, Base, BigIntPrimaryKeyMixin, TimestampMixin


class QuotationItem(BigIntPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "quotation_items"

    quotation_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("quotations.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[int | None] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("products.id", ondelete="SET NULL"),
    )
    sku_snapshot: Mapped[str] = mapped_column(String(120), nullable=False)
    name_snapshot: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[Decimal] = mapped_column(mysql.DECIMAL(19, 4), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(mysql.DECIMAL(19, 4), nullable=False)
    discount_rate: Mapped[Decimal] = mapped_column(
        mysql.DECIMAL(7, 4), nullable=False, default=0, server_default="0"
    )
    tax_rate: Mapped[Decimal] = mapped_column(
        mysql.DECIMAL(7, 4), nullable=False, default=0, server_default="0"
    )
    line_total: Mapped[Decimal] = mapped_column(mysql.DECIMAL(19, 4), nullable=False)
    sort_order: Mapped[int] = mapped_column(
        mysql.INTEGER(unsigned=True), nullable=False, default=0, server_default="0"
    )

    quotation = relationship("Quotation", back_populates="items")
    product = relationship("Product", lazy="raise")
