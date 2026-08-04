from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import (
    BIGINT_UNSIGNED,
    Base,
    BigIntPrimaryKeyMixin,
    PublicIdMixin,
    SoftDeleteMixin,
    TimestampMixin,
)
from app.db.types import UTCDateTime


class User(
    BigIntPrimaryKeyMixin,
    PublicIdMixin,
    TimestampMixin,
    SoftDeleteMixin,
    Base,
):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="tenant_email"),
        UniqueConstraint(
            "tenant_id",
            "feishu_open_id",
            name="uq_users_tenant_feishu_open_id",
        ),
        CheckConstraint(
            "status IN ('invited','active','locked','disabled')",
            name="status_allowed",
        ),
        CheckConstraint(
            "feishu_bind_status IN ('unbound','bound')",
            name="feishu_bind_status_allowed",
        ),
        Index("ix_users_tenant_status", "tenant_id", "status"),
    )

    tenant_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="invited", server_default="invited"
    )
    locale: Mapped[str] = mapped_column(
        String(16), nullable=False, default="en", server_default="en"
    )
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, default="UTC", server_default="UTC"
    )
    mfa_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    phone: Mapped[str | None] = mapped_column(String(32))
    feishu_open_id: Mapped[str | None] = mapped_column(String(128))
    feishu_name: Mapped[str | None] = mapped_column(String(120))
    feishu_bind_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="unbound", server_default="unbound"
    )
    feishu_bind_time: Mapped[datetime | None] = mapped_column(UTCDateTime())

    tenant = relationship("Tenant", lazy="raise")
    role_links = relationship(
        "UserRole",
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="UserRole.user_id",
        lazy="raise",
    )
    sales_profile = relationship(
        "SalesProfile",
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
        lazy="raise",
    )
