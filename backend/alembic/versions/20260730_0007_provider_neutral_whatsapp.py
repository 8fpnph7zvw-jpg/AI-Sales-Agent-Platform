"""Rename provider-specific WhatsApp session constraints.

Revision ID: 20260730_0007
Revises: 20260729_0006
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260730_0007"
down_revision: str | None = "20260729_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _replace_session_unique(table: str, desired_name: str) -> None:
    inspector = sa.inspect(op.get_bind())
    constraints = inspector.get_unique_constraints(table)
    matching = [
        constraint
        for constraint in constraints
        if constraint.get("name") and constraint.get("column_names") == ["session_id"]
    ]
    if any(constraint["name"] == desired_name for constraint in matching):
        return
    for constraint in matching:
        op.drop_constraint(constraint["name"], table, type_="unique")
    op.create_unique_constraint(desired_name, table, ["session_id"])


def upgrade() -> None:
    _replace_session_unique("connectors", "uq_connectors_provider_session")
    _replace_session_unique(
        "whatsapp_sessions",
        "uq_whatsapp_sessions_provider_session",
    )


def downgrade() -> None:
    # Constraint semantics do not change; only provider-neutral names are kept.
    pass
