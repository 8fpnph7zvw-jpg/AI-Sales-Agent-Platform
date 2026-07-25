from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BIGINT_UNSIGNED, Base
from app.db.types import UTCDateTime


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    permission_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.current_timestamp(), nullable=False
    )

    role = relationship("Role", back_populates="permission_links")
    permission = relationship("Permission", back_populates="role_links")
