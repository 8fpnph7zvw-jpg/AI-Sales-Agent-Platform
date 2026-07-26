"""Add RAG V3 document and embedding storage.

Revision ID: 20260725_0002
Revises: 20260724_0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision: str = "20260725_0002"
down_revision: str | None = "20260724_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "knowledge_documents" not in tables:
        op.create_table(
            "knowledge_documents",
            sa.Column("id", mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True),
            sa.Column("public_id", mysql.CHAR(26), nullable=False, unique=True),
            sa.Column(
                "tenant_id",
                mysql.BIGINT(unsigned=True),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "collection_id",
                mysql.BIGINT(unsigned=True),
                sa.ForeignKey("knowledge_collections.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("filename", sa.String(255), nullable=False),
            sa.Column("mime_type", sa.String(160), nullable=False),
            sa.Column("size_bytes", mysql.BIGINT(unsigned=True), nullable=False),
            sa.Column("sha256", mysql.CHAR(64), nullable=False),
            sa.Column("status", sa.String(24), nullable=False, server_default="processing"),
            sa.Column(
                "chunk_count", mysql.INTEGER(unsigned=True), nullable=False, server_default="0"
            ),
            sa.Column("error_message", sa.String(1000)),
            sa.Column(
                "uploaded_by",
                mysql.BIGINT(unsigned=True),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
            ),
            sa.Column("processed_at", sa.DateTime()),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.current_timestamp(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.current_timestamp(),
            ),
        )
        op.create_index(
            "ix_knowledge_documents_tenant_status", "knowledge_documents", ["tenant_id", "status"]
        )
        op.create_index(
            "ix_knowledge_documents_tenant_hash", "knowledge_documents", ["tenant_id", "sha256"]
        )
    chunk_columns = {column["name"]: column for column in inspector.get_columns("knowledge_chunks")}
    if not chunk_columns["knowledge_file_id"]["nullable"]:
        op.alter_column(
            "knowledge_chunks",
            "knowledge_file_id",
            existing_type=mysql.BIGINT(unsigned=True),
            nullable=True,
        )
    if "document_id" not in chunk_columns:
        op.add_column("knowledge_chunks", sa.Column("document_id", mysql.BIGINT(unsigned=True)))
        op.create_foreign_key(
            "fk_knowledge_chunks_document_id_knowledge_documents",
            "knowledge_chunks",
            "knowledge_documents",
            ["document_id"],
            ["id"],
            ondelete="CASCADE",
        )
        op.create_unique_constraint(
            "document_chunk_index", "knowledge_chunks", ["document_id", "chunk_index"]
        )
    if "embeddings" not in tables:
        op.create_table(
            "embeddings",
            sa.Column("id", mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True),
            sa.Column("public_id", mysql.CHAR(26), nullable=False, unique=True),
            sa.Column(
                "tenant_id",
                mysql.BIGINT(unsigned=True),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "chunk_id",
                mysql.BIGINT(unsigned=True),
                sa.ForeignKey("knowledge_chunks.id", ondelete="CASCADE"),
                nullable=False,
                unique=True,
            ),
            sa.Column("model", sa.String(120), nullable=False),
            sa.Column("dimensions", mysql.INTEGER(unsigned=True), nullable=False),
            sa.Column("vector", sa.JSON(), nullable=False),
            sa.Column("metadata", sa.JSON()),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.current_timestamp(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.current_timestamp(),
            ),
        )
        op.create_index("ix_embeddings_tenant_model", "embeddings", ["tenant_id", "model"])


def downgrade() -> None:
    op.drop_table("embeddings")
    op.drop_constraint("document_chunk_index", "knowledge_chunks", type_="unique")
    op.drop_constraint(
        "fk_knowledge_chunks_document_id_knowledge_documents",
        "knowledge_chunks",
        type_="foreignkey",
    )
    op.drop_column("knowledge_chunks", "document_id")
    op.alter_column(
        "knowledge_chunks",
        "knowledge_file_id",
        existing_type=mysql.BIGINT(unsigned=True),
        nullable=False,
    )
    op.drop_table("knowledge_documents")
