from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BIGINT_UNSIGNED, Base
from app.db.types import UTCDateTime


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    assigned_by: Mapped[int | None] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.current_timestamp(), nullable=False
    )

    user = relationship("User", foreign_keys=[user_id], back_populates="role_links")
    role = relationship("Role", back_populates="user_links")
    assigner = relationship("User", foreign_keys=[assigned_by], lazy="raise")
