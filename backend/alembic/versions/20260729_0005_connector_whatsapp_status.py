"""Mirror WhatsApp connection details on connectors.

Revision ID: 20260729_0005
Revises: 20260729_0004
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260729_0005"
down_revision: str | None = "20260729_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {
        column["name"] for column in sa.inspect(bind).get_columns("connectors")
    }
    if "phone" not in columns:
        op.add_column("connectors", sa.Column("phone", sa.String(32)))
    if "last_connected_at" not in columns:
        op.add_column("connectors", sa.Column("last_connected_at", sa.DateTime()))
    if "last_disconnect_reason" not in columns:
        op.add_column("connectors", sa.Column("last_disconnect_reason", sa.Text()))

    if bind.dialect.name == "mysql":
        op.execute(
            sa.text(
                "UPDATE connectors AS c "
                "JOIN whatsapp_sessions AS ws ON ws.connector_id = c.id "
                "AND ws.tenant_id = c.tenant_id "
                "SET c.phone = ws.phone, "
                "c.last_connected_at = ws.last_connected_at, "
                "c.last_disconnect_reason = CASE "
                "WHEN ws.status IN ('disconnected', 'error') THEN ws.last_error "
                "ELSE NULL END "
                "WHERE c.provider = 'whatsapp'"
            )
        )


def downgrade() -> None:
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("connectors")
    }
    if "last_disconnect_reason" in columns:
        op.drop_column("connectors", "last_disconnect_reason")
    if "last_connected_at" in columns:
        op.drop_column("connectors", "last_connected_at")
    if "phone" in columns:
        op.drop_column("connectors", "phone")
