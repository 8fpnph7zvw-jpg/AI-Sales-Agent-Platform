"""Classify conversation message sources without deleting existing rows.

Revision ID: 20260729_0006
Revises: 20260729_0005
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260729_0006"
down_revision: str | None = "20260729_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {
        column["name"] for column in inspector.get_columns("messages")
    }
    if "source" not in columns:
        op.add_column(
            "messages",
            sa.Column(
                "source",
                sa.String(24),
                nullable=True,
                server_default="web",
            ),
        )

    op.execute(
        sa.text(
            "UPDATE messages SET source = CASE "
            "WHEN external_message_id IS NOT NULL "
            "OR id IN ("
            "SELECT trigger_message_id FROM ai_agent_runs "
            "WHERE run_type = 'whatsapp_chat' AND trigger_message_id IS NOT NULL"
            ") "
            "OR id IN ("
            "SELECT output_message_id FROM ai_agent_runs "
            "WHERE run_type = 'whatsapp_chat' AND output_message_id IS NOT NULL"
            ") THEN 'whatsapp' "
            "WHEN direction = 'internal' "
            "OR id IN ("
            "SELECT trigger_message_id FROM ai_agent_runs "
            "WHERE run_type = 'chat' AND trigger_message_id IS NOT NULL"
            ") "
            "OR id IN ("
            "SELECT output_message_id FROM ai_agent_runs "
            "WHERE run_type = 'chat' AND output_message_id IS NOT NULL"
            ") THEN 'admin_test' "
            "ELSE 'web' END"
        )
    )
    op.alter_column(
        "messages",
        "source",
        existing_type=sa.String(24),
        nullable=False,
        server_default="web",
    )

    inspector = sa.inspect(bind)
    check_names = {
        constraint["name"]
        for constraint in inspector.get_check_constraints("messages")
        if constraint.get("name")
    }
    if "ck_messages_source_allowed" not in check_names:
        op.create_check_constraint(
            "ck_messages_source_allowed",
            "messages",
            "source IN ('whatsapp','admin_test','web')",
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    check_names = {
        constraint["name"]
        for constraint in inspector.get_check_constraints("messages")
        if constraint.get("name")
    }
    if "ck_messages_source_allowed" in check_names:
        op.drop_constraint(
            "ck_messages_source_allowed",
            "messages",
            type_="check",
        )
    columns = {
        column["name"] for column in inspector.get_columns("messages")
    }
    if "source" in columns:
        op.drop_column("messages", "source")
