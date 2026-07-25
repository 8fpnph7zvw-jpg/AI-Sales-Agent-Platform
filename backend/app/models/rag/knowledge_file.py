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
    SoftDeleteMixin,
    TimestampMixin,
)
from app.db.types import UTCDateTime


class KnowledgeFile(
    BigIntPrimaryKeyMixin,
    PublicIdMixin,
    TimestampMixin,
    SoftDeleteMixin,
    Base,
):
    __tablename__ = "knowledge_files"
    __table_args__ = (
        Index("ix_knowledge_files_collection_status", "collection_id", "status"),
        Index("ix_knowledge_files_tenant_hash", "tenant_id", "sha256"),
    )

    tenant_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    collection_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("knowledge_collections.id", ondelete="CASCADE"),
        nullable=False,
    )
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    mime_type: Mapped[str] = mapped_column(String(160), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BIGINT_UNSIGNED, nullable=False)
    sha256: Mapped[str] = mapped_column(mysql.CHAR(64), nullable=False)
    language: Mapped[str | None] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="uploaded", server_default="uploaded"
    )
    dify_document_id: Mapped[str | None] = mapped_column(String(128))
    version: Mapped[int] = mapped_column(
        mysql.INTEGER(unsigned=True), nullable=False, default=1, server_default="1"
    )
    error_message: Mapped[str | None] = mapped_column(String(1000))
    uploaded_by: Mapped[int | None] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    processed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    collection = relationship("KnowledgeCollection", back_populates="files")
    chunks = relationship(
        "KnowledgeChunk",
        back_populates="knowledge_file",
        cascade="all, delete-orphan",
        lazy="raise",
    )
