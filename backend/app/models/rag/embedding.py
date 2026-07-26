from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, String
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BIGINT_UNSIGNED, Base, BigIntPrimaryKeyMixin, PublicIdMixin, TimestampMixin


class Embedding(BigIntPrimaryKeyMixin, PublicIdMixin, TimestampMixin, Base):
    __tablename__ = "embeddings"
    __table_args__ = (Index("ix_embeddings_tenant_model", "tenant_id", "model"),)

    tenant_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    chunk_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("knowledge_chunks.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    dimensions: Mapped[int] = mapped_column(mysql.INTEGER(unsigned=True), nullable=False)
    vector: Mapped[list[float]] = mapped_column(JSON, nullable=False)
    vector_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON)

    chunk = relationship("KnowledgeChunk", back_populates="embedding")
