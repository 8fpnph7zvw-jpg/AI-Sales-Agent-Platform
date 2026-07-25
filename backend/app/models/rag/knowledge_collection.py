from __future__ import annotations

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import (
    BIGINT_UNSIGNED,
    Base,
    BigIntPrimaryKeyMixin,
    PublicIdMixin,
    SoftDeleteMixin,
    TimestampMixin,
)


class KnowledgeCollection(
    BigIntPrimaryKeyMixin,
    PublicIdMixin,
    TimestampMixin,
    SoftDeleteMixin,
    Base,
):
    __tablename__ = "knowledge_collections"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="tenant_name"),)

    tenant_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000))
    dify_dataset_id: Mapped[str | None] = mapped_column(String(128))
    embedding_provider: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="active", server_default="active"
    )
    created_by: Mapped[int | None] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("users.id", ondelete="SET NULL"),
    )

    files = relationship(
        "KnowledgeFile",
        back_populates="collection",
        cascade="all, delete-orphan",
        lazy="raise",
    )
