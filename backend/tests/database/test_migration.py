from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import Mock

import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REVISION_FILE = BACKEND_ROOT / "alembic" / "versions" / "20260724_0001_initial_schema.py"
QUOTATION_REVISION_FILE = (
    BACKEND_ROOT
    / "alembic"
    / "versions"
    / "20260803_0010_quotation_status_soft_delete.py"
)


def _load_revision():
    spec = importlib.util.spec_from_file_location("initial_schema_revision", REVISION_FILE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_quotation_revision():
    spec = importlib.util.spec_from_file_location(
        "quotation_status_soft_delete_revision",
        QUOTATION_REVISION_FILE,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _mock_quotation_upgrade(monkeypatch, *, check_constraints=()):
    revision = _load_quotation_revision()
    inspector = Mock()
    inspector.get_columns.return_value = [{"name": "id"}, {"name": "status"}]
    inspector.get_check_constraints.return_value = [
        {"name": name} for name in check_constraints
    ]
    inspector.get_indexes.return_value = []

    monkeypatch.setattr(revision.sa, "inspect", lambda _bind: inspector)
    monkeypatch.setattr(revision.op, "get_bind", Mock(return_value=object()))
    monkeypatch.setattr(revision.op, "f", lambda name: name)

    events: list[str] = []

    def operation(name: str) -> Mock:
        return Mock(side_effect=lambda *_args, **_kwargs: events.append(name))

    operations = {
        "drop_constraint": operation("drop_constraint"),
        "execute": operation("execute"),
        "alter_column": operation("alter_column"),
        "create_check_constraint": operation("create_check_constraint"),
        "add_column": operation("add_column"),
        "create_index": operation("create_index"),
    }
    for name, mock in operations.items():
        monkeypatch.setattr(revision.op, name, mock)
    return revision, operations, events


def test_alembic_has_one_linear_head() -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    scripts = ScriptDirectory.from_config(config)
    assert scripts.get_heads() == ["20260803_0010"]
    assert scripts.get_base() == "20260724_0001"


def test_baseline_sql_files_exist_and_split_into_statements() -> None:
    revision = _load_revision()
    schema = revision.DATABASE_INIT / "001_schema.sql"
    permissions = revision.DATABASE_INIT / "002_permissions_seed.sql"

    schema_statements = list(revision._statements(schema))
    permission_statements = list(revision._statements(permissions))

    assert len([item for item in schema_statements if item.startswith("CREATE TABLE")]) == 33
    assert len(permission_statements) == 1
    assert permission_statements[0].startswith("INSERT INTO permissions")


def test_quotation_upgrade_without_old_constraint_does_not_drop(monkeypatch) -> None:
    revision, operations, events = _mock_quotation_upgrade(monkeypatch)
    revision.upgrade()

    operations["drop_constraint"].assert_not_called()
    assert events == [
        "execute",
        "alter_column",
        "create_check_constraint",
        "add_column",
        "create_index",
    ]
    operations["alter_column"].assert_called_once()
    alter_status_args = operations["alter_column"].call_args
    assert alter_status_args.args == ("quotations", "status")
    assert alter_status_args.kwargs["existing_type"].length == 24
    assert alter_status_args.kwargs["nullable"] is False
    assert alter_status_args.kwargs["server_default"] == "pending"
    operations["create_check_constraint"].assert_called_once_with(
        "ck_quotations_status_allowed",
        "quotations",
        "status IN ('pending','quoted','won','lost','cancelled')",
    )
    deleted_at = operations["add_column"].call_args.args[1]
    assert deleted_at.name == "deleted_at"
    assert deleted_at.type.fsp == 6
    operations["create_index"].assert_called_once_with(
        "ix_quotations_tenant_deleted",
        "quotations",
        ["tenant_id", "deleted_at"],
    )


def test_quotation_upgrade_drops_existing_constraint_before_data_update(monkeypatch) -> None:
    revision, operations, events = _mock_quotation_upgrade(
        monkeypatch,
        check_constraints=("ck_quotations_status_allowed",),
    )

    revision.upgrade()

    operations["drop_constraint"].assert_called_once_with(
        "ck_quotations_status_allowed",
        "quotations",
        type_="check",
    )
    assert events[:4] == [
        "drop_constraint",
        "execute",
        "alter_column",
        "create_check_constraint",
    ]


def test_quotation_status_migration_converts_legacy_values() -> None:
    revision = _load_quotation_revision()
    engine = sa.create_engine("sqlite://")

    with engine.begin() as connection:
        connection.execute(sa.text("CREATE TABLE quotations (status VARCHAR(24) NOT NULL)"))
        connection.execute(
            sa.text("INSERT INTO quotations (status) VALUES ('draft'), ('accepted')")
        )
        connection.execute(revision.STATUS_MIGRATION_SQL)
        statuses = list(
            connection.execute(sa.text("SELECT status FROM quotations ORDER BY rowid")).scalars()
        )

    assert statuses == ["pending", "won"]
