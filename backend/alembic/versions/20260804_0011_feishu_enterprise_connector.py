"""Move Feishu identities from sales profiles to users.

Revision ID: 20260804_0011
Revises: 20260803_0010
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "20260804_0011"
down_revision: str | None = "20260803_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("feishu_open_id", sa.String(128), nullable=True))
    op.add_column("users", sa.Column("feishu_name", sa.String(120), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "feishu_bind_status",
            sa.String(16),
            nullable=False,
            server_default="unbound",
        ),
    )
    op.add_column(
        "users",
        sa.Column("feishu_bind_time", mysql.DATETIME(fsp=6), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE users AS u "
            "JOIN sales_profiles AS sp ON sp.user_id = u.id "
            "SET u.feishu_open_id = sp.feishu_open_id, "
            "u.feishu_bind_status = CASE "
            "WHEN sp.feishu_open_id IS NULL OR sp.feishu_open_id = '' "
            "THEN 'unbound' ELSE 'bound' END, "
            "u.feishu_bind_time = CASE "
            "WHEN sp.feishu_open_id IS NULL OR sp.feishu_open_id = '' "
            "THEN NULL ELSE CURRENT_TIMESTAMP(6) END"
        )
    )
    op.create_unique_constraint(
        "uq_users_tenant_feishu_open_id",
        "users",
        ["tenant_id", "feishu_open_id"],
    )
    op.create_check_constraint(
        "ck_users_feishu_bind_status_allowed",
        "users",
        "feishu_bind_status IN ('unbound','bound')",
    )
    op.drop_constraint("tenant_feishu_open_id", "sales_profiles", type_="unique")
    op.drop_column("sales_profiles", "feishu_open_id")


def downgrade() -> None:
    op.add_column(
        "sales_profiles",
        sa.Column("feishu_open_id", sa.String(128), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE sales_profiles AS sp "
            "JOIN users AS u ON u.id = sp.user_id "
            "SET sp.feishu_open_id = u.feishu_open_id"
        )
    )
    op.create_unique_constraint(
        "tenant_feishu_open_id",
        "sales_profiles",
        ["tenant_id", "feishu_open_id"],
    )
    op.drop_constraint(
        "ck_users_feishu_bind_status_allowed",
        "users",
        type_="check",
    )
    op.drop_constraint(
        "uq_users_tenant_feishu_open_id",
        "users",
        type_="unique",
    )
    op.drop_column("users", "feishu_bind_time")
    op.drop_column("users", "feishu_bind_status")
    op.drop_column("users", "feishu_name")
    op.drop_column("users", "feishu_open_id")
