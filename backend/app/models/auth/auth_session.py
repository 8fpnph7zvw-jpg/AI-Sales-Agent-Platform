from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import (
    BIGINT_UNSIGNED,
    Base,
    BigIntPrimaryKeyMixin,
    PublicIdMixin,
    TimestampMixin,
)
from app.db.types import UTCDateTime


class AuthSession(BigIntPrimaryKeyMixin, PublicIdMixin, TimestampMixin, Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        Index("ix_auth_sessions_user_active", "user_id", "revoked_at", "expires_at"),
        Index("ix_auth_sessions_token_family", "token_family_id"),
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
    refresh_token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    token_family_id: Mapped[str] = mapped_column(mysql.CHAR(26), nullable=False)
    ip_hash: Mapped[str | None] = mapped_column(String(128))
    user_agent_hash: Mapped[str | None] = mapped_column(String(128))
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    revoke_reason: Mapped[str | None] = mapped_column(String(120))

    user = relationship("User", lazy="raise")
