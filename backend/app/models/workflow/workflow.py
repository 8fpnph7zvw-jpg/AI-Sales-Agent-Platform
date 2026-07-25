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
    SoftDeleteMixin,
    TimestampMixin,
)
from app.db.types import UTCDateTime


class Workflow(
    BigIntPrimaryKeyMixin,
    PublicIdMixin,
    TimestampMixin,
    SoftDeleteMixin,
    Base,
):
    __tablename__ = "workflows"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", "version", name="tenant_name_version"),
        CheckConstraint(
            "status IN ('draft','published','active','inactive','retired')",
            name="status_allowed",
        ),
    )

    tenant_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="draft", server_default="draft"
    )
    version: Mapped[int] = mapped_column(mysql.INTEGER(unsigned=True), nullable=False)
    definition: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    n8n_workflow_id: Mapped[str | None] = mapped_column(String(128))
    last_published_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_by: Mapped[int | None] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    updated_by: Mapped[int | None] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("users.id", ondelete="SET NULL"),
    )

    nodes = relationship(
        "WorkflowNode",
        back_populates="workflow",
        cascade="all, delete-orphan",
        lazy="raise",
    )
