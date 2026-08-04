"""Add user phone and secure Feishu OAuth state.

Revision ID: 20260804_0012
Revises: 20260804_0011
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision: str = "20260804_0012"
down_revision: str | None = "20260804_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    if "phone" not in user_columns:
        op.add_column("users", sa.Column("phone", sa.String(32), nullable=True))

    table_exists = inspector.has_table("feishu_oauth_states")
    table_preexisted = table_exists
    if not table_exists:
        op.create_table(
            "feishu_oauth_states",
            sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
            sa.Column("tenant_id", mysql.BIGINT(unsigned=True), nullable=False),
            sa.Column("user_id", mysql.BIGINT(unsigned=True), nullable=False),
            sa.Column("initiated_by", mysql.BIGINT(unsigned=True), nullable=True),
            sa.Column("state_hash", sa.String(64), nullable=False),
            sa.Column("code_verifier", sa.String(128), nullable=False),
            sa.Column("redirect_uri", sa.String(512), nullable=False),
            sa.Column("expires_at", mysql.DATETIME(fsp=6), nullable=False),
            sa.Column("consumed_at", mysql.DATETIME(fsp=6), nullable=True),
            sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
            sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["initiated_by"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("state_hash", name="uq_feishu_oauth_states_state_hash"),
        )
        table_exists = True

    if table_exists:
        inspector = sa.inspect(bind)
        if table_preexisted:
            oauth_columns = {
                item["name"]: item
                for item in inspector.get_columns("feishu_oauth_states")
            }
            for column_name in ("created_at", "updated_at"):
                column = oauth_columns.get(column_name)
                if column is not None and column.get("default") is not None:
                    op.alter_column(
                        "feishu_oauth_states",
                        column_name,
                        existing_type=mysql.DATETIME(fsp=6),
                        existing_nullable=False,
                        server_default=None,
                    )
        indexes = {
            item["name"] for item in inspector.get_indexes("feishu_oauth_states")
        }
        if "ix_feishu_oauth_states_expires" not in indexes:
            op.create_index(
                "ix_feishu_oauth_states_expires",
                "feishu_oauth_states",
                ["expires_at"],
            )
        if "ix_feishu_oauth_states_user" not in indexes:
            op.create_index(
                "ix_feishu_oauth_states_user",
                "feishu_oauth_states",
                ["tenant_id", "user_id"],
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("feishu_oauth_states"):
        indexes = {
            item["name"] for item in inspector.get_indexes("feishu_oauth_states")
        }
        if "ix_feishu_oauth_states_user" in indexes:
            op.drop_index("ix_feishu_oauth_states_user", table_name="feishu_oauth_states")
        if "ix_feishu_oauth_states_expires" in indexes:
            op.drop_index("ix_feishu_oauth_states_expires", table_name="feishu_oauth_states")
        op.drop_table("feishu_oauth_states")
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    if "phone" in user_columns:
        op.drop_column("users", "phone")
