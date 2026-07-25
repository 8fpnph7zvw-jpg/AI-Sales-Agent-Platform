from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigIntPrimaryKeyMixin, TimestampMixin


class Permission(BigIntPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    resource: Mapped[str] = mapped_column(String(80), nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    role_links = relationship(
        "RolePermission",
        back_populates="permission",
        cascade="all, delete-orphan",
        lazy="raise",
    )
