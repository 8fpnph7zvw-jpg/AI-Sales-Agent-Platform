from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BIGINT_UNSIGNED, Base, BigIntPrimaryKeyMixin
from app.db.types import UTCDateTime


class SalesProfile(BigIntPrimaryKeyMixin, Base):
    __tablename__ = "sales_profiles"
    __table_args__ = (
        UniqueConstraint("user_id", name="user_id"),
        Index("ix_sales_profiles_tenant_name", "tenant_id", "sales_name"),
    )

    tenant_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    sales_name: Mapped[str] = mapped_column(String(120), nullable=False)
    created_time: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        server_default=func.current_timestamp(),
    )

    user = relationship("User", back_populates="sales_profile", lazy="raise")
