from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, ForeignKey, String, UniqueConstraint
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


class Prompt(BigIntPrimaryKeyMixin, PublicIdMixin, TimestampMixin, Base):
    __tablename__ = "prompts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "prompt_key", "version", name="tenant_key_version"),
        CheckConstraint(
            "status IN ('draft','published','retired')",
            name="status_allowed",
        ),
    )

    tenant_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    prompt_key: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[int] = mapped_column(mysql.INTEGER(unsigned=True), nullable=False)
    purpose: Mapped[str | None] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(mysql.MEDIUMTEXT, nullable=False)
    variables_schema: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    output_schema: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="draft", server_default="draft"
    )
    dify_app_id: Mapped[str | None] = mapped_column(String(128))
    created_by: Mapped[int | None] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    published_by: Mapped[int | None] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    tenant = relationship("Tenant", lazy="raise")
