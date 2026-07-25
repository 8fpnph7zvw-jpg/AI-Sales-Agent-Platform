"""Create the MySQL baseline schema and permission catalog.

Revision ID: 20260724_0001
Revises:
Create Date: 2026-07-24
"""

from collections.abc import Iterator, Sequence
from pathlib import Path

import sqlalchemy as sa

from alembic import op

revision: str = "20260724_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DATABASE_INIT = REPOSITORY_ROOT / "database" / "init"


def _statements(path: Path) -> Iterator[str]:
    """Split the checked-in baseline SQL.

    Baseline files intentionally contain no procedures, triggers, or semicolons
    inside string literals. Future migrations must use explicit Alembic ops.
    """

    sql = path.read_text(encoding="utf-8")
    uncommented = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
    for statement in uncommented.split(";"):
        if stripped := statement.strip():
            yield stripped


def _run_sql_file(filename: str) -> None:
    path = DATABASE_INIT / filename
    if not path.is_file():
        raise RuntimeError(f"Required baseline SQL file is missing: {path}")
    for statement in _statements(path):
        op.execute(sa.text(statement))


def upgrade() -> None:
    _run_sql_file("001_schema.sql")
    _run_sql_file("002_permissions_seed.sql")


def downgrade() -> None:
    # MySQL DDL auto-commits. Drop in strict reverse dependency order.
    for table_name in (
        "outbox_events",
        "audit_logs",
        "webhook_logs",
        "system_configs",
        "notifications",
        "workflow_nodes",
        "workflows",
        "quotation_items",
        "quotations",
        "products",
        "knowledge_chunks",
        "knowledge_files",
        "knowledge_collections",
        "ai_agent_runs",
        "messages",
        "conversations",
        "prompts",
        "customer_sessions",
        "connector_configs",
        "connectors",
        "customers",
        "auth_sessions",
        "role_permissions",
        "user_roles",
        "roles",
        "users",
        "permissions",
        "tenants",
    ):
        op.drop_table(table_name)
