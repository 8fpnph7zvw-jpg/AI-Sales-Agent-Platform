from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import (
    BIGINT_UNSIGNED,
    Base,
    BigIntPrimaryKeyMixin,
    PublicIdMixin,
    TimestampMixin,
)


class WorkflowNode(BigIntPrimaryKeyMixin, PublicIdMixin, TimestampMixin, Base):
    __tablename__ = "workflow_nodes"
    __table_args__ = (UniqueConstraint("workflow_id", "node_key", name="workflow_node_key"),)

    tenant_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    workflow_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
    )
    node_key: Mapped[str] = mapped_column(String(100), nullable=False)
    node_type: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    config: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    position: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    sort_order: Mapped[int] = mapped_column(
        mysql.INTEGER(unsigned=True), nullable=False, default=0, server_default="0"
    )

    workflow = relationship("Workflow", back_populates="nodes")
