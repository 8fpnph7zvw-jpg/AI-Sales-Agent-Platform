"""Add durable WhatsApp provider binding and session diagnostics.

Revision ID: 20260729_0004
Revises: 20260728_0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision: str = "20260729_0004"
down_revision: str | None = "20260728_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    connector_columns = {
        column["name"] for column in inspector.get_columns("connectors")
    }
    if "session_id" not in connector_columns:
        op.add_column("connectors", sa.Column("session_id", sa.String(64)))

    session_columns = {
        column["name"] for column in inspector.get_columns("whatsapp_sessions")
    }
    if "last_error" not in session_columns:
        op.add_column("whatsapp_sessions", sa.Column("last_error", sa.Text()))
    if "session_data" not in session_columns:
        op.add_column("whatsapp_sessions", sa.Column("session_data", mysql.JSON()))

    # Keep the Connector row as a directly queryable mirror of the canonical,
    # tenant-owned whatsapp_sessions binding.
    op.execute(
        sa.text(
            "UPDATE connectors AS c "
            "JOIN whatsapp_sessions AS ws ON ws.connector_id = c.id "
            "AND ws.tenant_id = c.tenant_id "
            "SET c.session_id = ws.session_id "
            "WHERE c.provider = 'whatsapp' AND ws.session_id IS NOT NULL"
        )
    )

    inspector = sa.inspect(bind)
    connector_unique_names = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("connectors")
        if constraint.get("name")
    }
    if "uq_connectors_provider_session" not in connector_unique_names:
        op.create_unique_constraint(
            "uq_connectors_provider_session",
            "connectors",
            ["session_id"],
        )
    if "uq_connectors_id_tenant" not in connector_unique_names:
        op.create_unique_constraint(
            "uq_connectors_id_tenant",
            "connectors",
            ["id", "tenant_id"],
        )

    inspector = sa.inspect(bind)
    session_foreign_key_names = {
        constraint["name"]
        for constraint in inspector.get_foreign_keys("whatsapp_sessions")
        if constraint.get("name")
    }
    if "fk_whatsapp_sessions_connector_tenant" not in session_foreign_key_names:
        op.create_foreign_key(
            "fk_whatsapp_sessions_connector_tenant",
            "whatsapp_sessions",
            "connectors",
            ["connector_id", "tenant_id"],
            ["id", "tenant_id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    session_foreign_key_names = {
        constraint["name"]
        for constraint in inspector.get_foreign_keys("whatsapp_sessions")
        if constraint.get("name")
    }
    if "fk_whatsapp_sessions_connector_tenant" in session_foreign_key_names:
        op.drop_constraint(
            "fk_whatsapp_sessions_connector_tenant",
            "whatsapp_sessions",
            type_="foreignkey",
        )
    connector_unique_names = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("connectors")
        if constraint.get("name")
    }
    if "uq_connectors_provider_session" in connector_unique_names:
        op.drop_constraint(
            "uq_connectors_provider_session",
            "connectors",
            type_="unique",
        )
    if "uq_connectors_id_tenant" in connector_unique_names:
        op.drop_constraint(
            "uq_connectors_id_tenant",
            "connectors",
            type_="unique",
        )
    session_columns = {
        column["name"] for column in inspector.get_columns("whatsapp_sessions")
    }
    if "session_data" in session_columns:
        op.drop_column("whatsapp_sessions", "session_data")
    if "last_error" in session_columns:
        op.drop_column("whatsapp_sessions", "last_error")
    connector_columns = {
        column["name"] for column in inspector.get_columns("connectors")
    }
    if "session_id" in connector_columns:
        op.drop_column("connectors", "session_id")
