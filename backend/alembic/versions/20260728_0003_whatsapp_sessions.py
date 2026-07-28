"""Persist tenant-scoped OpenWA session lifecycle state.

Revision ID: 20260728_0003
Revises: 20260725_0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision: str = "20260728_0003"
down_revision: str | None = "20260725_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "whatsapp_sessions" in set(inspector.get_table_names()):
        return
    op.create_table(
        "whatsapp_sessions",
        sa.Column(
            "id",
            mysql.BIGINT(unsigned=True),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column(
            "tenant_id",
            mysql.BIGINT(unsigned=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "connector_id",
            mysql.BIGINT(unsigned=True),
            sa.ForeignKey("connectors.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("session_id", sa.String(64)),
        sa.Column("session_name", sa.String(100), nullable=False),
        sa.Column("phone", sa.String(32)),
        sa.Column("status", sa.String(24), nullable=False, server_default="created"),
        sa.Column("qr_code", mysql.MEDIUMTEXT()),
        sa.Column("last_connected_at", sa.DateTime()),
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
        sa.CheckConstraint(
            "status IN "
            "('created','starting','waiting_qr','connected','disconnected','error')",
            name="ck_whatsapp_sessions_status_allowed",
        ),
        sa.UniqueConstraint(
            "connector_id",
            name="uq_whatsapp_sessions_connector",
        ),
        sa.UniqueConstraint(
            "session_id",
            name="uq_whatsapp_sessions_openwa_session",
        ),
        sa.UniqueConstraint(
            "session_name",
            name="uq_whatsapp_sessions_session_name",
        ),
    )
    op.create_index(
        "ix_whatsapp_sessions_tenant_status",
        "whatsapp_sessions",
        ["tenant_id", "status"],
    )
    op.create_index(
        "ix_whatsapp_sessions_tenant_connector",
        "whatsapp_sessions",
        ["tenant_id", "connector_id"],
    )


def downgrade() -> None:
    op.drop_table("whatsapp_sessions")
