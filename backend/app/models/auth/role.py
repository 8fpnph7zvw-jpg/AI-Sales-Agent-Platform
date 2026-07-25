from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import (
    BIGINT_UNSIGNED,
    Base,
    BigIntPrimaryKeyMixin,
    PublicIdMixin,
    TimestampMixin,
)


class Role(BigIntPrimaryKeyMixin, PublicIdMixin, TimestampMixin, Base):
    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="tenant_code"),)

    tenant_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_system: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )

    tenant = relationship("Tenant", lazy="raise")
    user_links = relationship(
        "UserRole",
        back_populates="role",
        cascade="all, delete-orphan",
        lazy="raise",
    )
    permission_links = relationship(
        "RolePermission",
        back_populates="role",
        cascade="all, delete-orphan",
        lazy="raise",
    )
