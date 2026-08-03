"""Add quotation lifecycle statuses and soft deletion.

Revision ID: 20260803_0010
Revises: 20260802_0009
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260803_0010"
down_revision: str | None = "20260802_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("quotations")}
    if "deleted_at" in columns:
        return
    op.execute(
        sa.text(
            """UPDATE quotations SET status = CASE
            WHEN status IN ('draft','pending_approval','approved','sent') THEN 'pending'
            WHEN status = 'accepted' THEN 'won'
            WHEN status IN ('rejected','expired') THEN 'lost'
            ELSE 'cancelled' END"""
        )
    )
    op.alter_column(
        "quotations",
        "status",
        existing_type=sa.String(length=24),
        nullable=False,
        server_default="pending",
    )
    op.create_check_constraint(
        op.f("ck_quotations_status_allowed"),
        "quotations",
        "status IN ('pending','won','lost','cancelled')",
    )
    op.add_column("quotations", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    op.create_index(
        "ix_quotations_tenant_deleted_created",
        "quotations",
        ["tenant_id", "deleted_at", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_quotations_tenant_deleted_created", table_name="quotations")
    op.drop_column("quotations", "deleted_at")
    op.drop_constraint(
        op.f("ck_quotations_status_allowed"),
        "quotations",
        type_="check",
    )
    op.execute(
        sa.text(
            """UPDATE quotations SET status = CASE
            WHEN status = 'pending' THEN 'draft'
            WHEN status = 'won' THEN 'accepted'
            WHEN status = 'lost' THEN 'rejected'
            ELSE 'cancelled' END"""
        )
    )
    op.alter_column(
        "quotations",
        "status",
        existing_type=sa.String(length=24),
        nullable=False,
        server_default="draft",
    )
    op.create_check_constraint(
        op.f("ck_quotations_status_allowed"),
        "quotations",
        "status IN ('draft','pending_approval','approved','sent','accepted',"
        "'rejected','expired','cancelled')",
    )
