from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BIGINT_UNSIGNED, Base, BigIntPrimaryKeyMixin, PublicIdMixin, TimestampMixin
from app.db.types import UTCDateTime


class KnowledgeDocument(BigIntPrimaryKeyMixin, PublicIdMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        Index("ix_knowledge_documents_tenant_status", "tenant_id", "status"),
        Index("ix_knowledge_documents_tenant_hash", "tenant_id", "sha256"),
    )

    tenant_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    collection_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED, ForeignKey("knowledge_collections.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(160), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BIGINT_UNSIGNED, nullable=False)
    sha256: Mapped[str] = mapped_column(mysql.CHAR(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="processing", server_default="processing"
    )
    chunk_count: Mapped[int] = mapped_column(
        mysql.INTEGER(unsigned=True), nullable=False, default=0, server_default="0"
    )
    error_message: Mapped[str | None] = mapped_column(String(1000))
    uploaded_by: Mapped[int | None] = mapped_column(
        BIGINT_UNSIGNED, ForeignKey("users.id", ondelete="SET NULL")
    )
    processed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    collection = relationship("KnowledgeCollection")
    chunks = relationship(
        "KnowledgeChunk", back_populates="document", cascade="all, delete-orphan", lazy="raise"
    )
