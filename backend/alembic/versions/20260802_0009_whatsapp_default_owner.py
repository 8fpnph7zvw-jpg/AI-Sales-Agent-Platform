"""Add a default sales owner reference to connector configuration.

Revision ID: 20260802_0009
Revises: 20260802_0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision: str = "20260802_0009"
down_revision: str | None = "20260802_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "connector_configs",
        sa.Column(
            "default_owner_user_id",
            mysql.BIGINT(unsigned=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_connector_configs_default_owner_user_id_users",
        "connector_configs",
        "users",
        ["default_owner_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_connector_configs_default_owner_user_id",
        "connector_configs",
        ["default_owner_user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_connector_configs_default_owner_user_id",
        table_name="connector_configs",
    )
    op.drop_constraint(
        "fk_connector_configs_default_owner_user_id_users",
        "connector_configs",
        type_="foreignkey",
    )
    op.drop_column("connector_configs", "default_owner_user_id")
