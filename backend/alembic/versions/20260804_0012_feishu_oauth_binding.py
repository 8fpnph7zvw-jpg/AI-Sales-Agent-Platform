"""Add user phone and secure Feishu OAuth state.

Revision ID: 20260804_0012
Revises: 20260804_0011
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "20260804_0012"
down_revision: str | None = "20260804_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("phone", sa.String(32), nullable=True))
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
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["initiated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state_hash", name="uq_feishu_oauth_states_state_hash"),
    )
    op.create_index(
        "ix_feishu_oauth_states_expires",
        "feishu_oauth_states",
        ["expires_at"],
    )
    op.create_index(
        "ix_feishu_oauth_states_user",
        "feishu_oauth_states",
        ["tenant_id", "user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_feishu_oauth_states_user", table_name="feishu_oauth_states")
    op.drop_index("ix_feishu_oauth_states_expires", table_name="feishu_oauth_states")
    op.drop_table("feishu_oauth_states")
    op.drop_column("users", "phone")
