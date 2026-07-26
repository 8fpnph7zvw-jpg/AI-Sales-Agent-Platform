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


class KnowledgeChunk(BigIntPrimaryKeyMixin, PublicIdMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint("knowledge_file_id", "chunk_index", name="file_chunk_index"),
        UniqueConstraint("document_id", "chunk_index", name="document_chunk_index"),
    )

    tenant_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    knowledge_file_id: Mapped[int | None] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("knowledge_files.id", ondelete="CASCADE"),
        nullable=True,
    )
    document_id: Mapped[int | None] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
    )
    chunk_index: Mapped[int] = mapped_column(mysql.INTEGER(unsigned=True), nullable=False)
    content_text: Mapped[str] = mapped_column(mysql.MEDIUMTEXT, nullable=False)
    content_hash: Mapped[str] = mapped_column(mysql.CHAR(64), nullable=False)
    token_count: Mapped[int | None] = mapped_column(mysql.INTEGER(unsigned=True))
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON)
    dify_segment_id: Mapped[str | None] = mapped_column(String(128))
    sync_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="pending", server_default="pending"
    )

    knowledge_file = relationship("KnowledgeFile", back_populates="chunks")
    document = relationship("KnowledgeDocument", back_populates="chunks")
    embedding = relationship(
        "Embedding", back_populates="chunk", uselist=False, cascade="all, delete-orphan"
    )
