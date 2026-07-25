from __future__ import annotations

from sqlalchemy import CheckConstraint, Index, String
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import (
    Base,
    BigIntPrimaryKeyMixin,
    PublicIdMixin,
    SoftDeleteMixin,
    TimestampMixin,
)


class Tenant(
    BigIntPrimaryKeyMixin,
    PublicIdMixin,
    TimestampMixin,
    SoftDeleteMixin,
    Base,
):
    __tablename__ = "tenants"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active','suspended','closed')",
            name="status_allowed",
        ),
        Index("ix_tenants_status", "status"),
    )

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="active", server_default="active"
    )
    plan_code: Mapped[str] = mapped_column(
        String(50), nullable=False, default="standard", server_default="standard"
    )
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, default="UTC", server_default="UTC"
    )
    default_currency: Mapped[str] = mapped_column(
        mysql.CHAR(3), nullable=False, default="USD", server_default="USD"
    )
    data_region: Mapped[str | None] = mapped_column(String(32))
