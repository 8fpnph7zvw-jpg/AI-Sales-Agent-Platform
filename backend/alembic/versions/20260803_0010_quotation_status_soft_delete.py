"""Add quotation lifecycle statuses and soft deletion.

Revision ID: 20260803_0010
Revises: 20260802_0009
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision: str = "20260803_0010"
down_revision: str | None = "20260802_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUS_CONSTRAINT = "ck_quotations_status_allowed"
SOFT_DELETE_INDEX = "ix_quotations_tenant_deleted"
STATUS_MIGRATION_SQL = sa.text(
    """UPDATE quotations SET status = CASE
    WHEN status IN ('draft','pending_approval','approved','sent') THEN 'pending'
    WHEN status = 'accepted' THEN 'won'
    WHEN status IN ('rejected','expired') THEN 'lost'
    ELSE 'cancelled' END"""
)


def _names(items: list[dict[str, object]]) -> set[str]:
    return {str(item["name"]) for item in items if item.get("name")}


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = _names(inspector.get_columns("quotations"))
    constraints = _names(inspector.get_check_constraints("quotations"))
    indexes = inspector.get_indexes("quotations")
    index_names = _names(indexes)
    has_soft_delete_index = any(
        list(index.get("column_names") or ())[:2] == ["tenant_id", "deleted_at"]
        for index in indexes
    )

    # Production databases may or may not have the constraint from the old
    # schema. It must be absent while legacy status values are converted.
    if STATUS_CONSTRAINT in constraints:
        op.drop_constraint(
            op.f(STATUS_CONSTRAINT),
            "quotations",
            type_="check",
        )

    # A checked-in baseline can already contain the soft-delete column. In that
    # case its statuses are already normalized and must not be rewritten.
    if "deleted_at" not in columns:
        op.execute(STATUS_MIGRATION_SQL)

    op.alter_column(
        "quotations",
        "status",
        existing_type=sa.String(length=24),
        nullable=False,
        server_default="pending",
    )
    op.create_check_constraint(
        op.f(STATUS_CONSTRAINT),
        "quotations",
        "status IN ('pending','quoted','won','lost','cancelled')",
    )

    if "deleted_at" not in columns:
        op.add_column(
            "quotations",
            sa.Column("deleted_at", mysql.DATETIME(fsp=6), nullable=True),
        )
    if SOFT_DELETE_INDEX not in index_names and not has_soft_delete_index:
        op.create_index(
            SOFT_DELETE_INDEX,
            "quotations",
            ["tenant_id", "deleted_at"],
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = _names(inspector.get_columns("quotations"))
    constraints = _names(inspector.get_check_constraints("quotations"))
    indexes = _names(inspector.get_indexes("quotations"))

    if STATUS_CONSTRAINT in constraints:
        op.drop_constraint(
            op.f(STATUS_CONSTRAINT),
            "quotations",
            type_="check",
        )
    if SOFT_DELETE_INDEX in indexes:
        op.drop_index(SOFT_DELETE_INDEX, table_name="quotations")
    if "deleted_at" in columns:
        op.drop_column("quotations", "deleted_at")

    # Do not reverse normalized status values: multiple legacy values map to
    # "pending", so reversing them would modify customer quotation history.
    op.alter_column(
        "quotations",
        "status",
        existing_type=sa.String(length=24),
        nullable=False,
        server_default="draft",
    )
