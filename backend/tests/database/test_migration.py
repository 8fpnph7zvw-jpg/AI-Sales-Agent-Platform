from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import Mock

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


def test_quotation_upgrade_does_not_drop_missing_check_constraint(monkeypatch) -> None:
    revision = _load_quotation_revision()
    inspector = Mock()
    inspector.get_columns.return_value = [{"name": "id"}, {"name": "status"}]

    monkeypatch.setattr(revision.sa, "inspect", lambda _bind: inspector)
    monkeypatch.setattr(revision.op, "get_bind", Mock(return_value=object()))
    drop_constraint = Mock()
    monkeypatch.setattr(revision.op, "drop_constraint", drop_constraint)
    monkeypatch.setattr(revision.op, "execute", Mock())
    alter_column = Mock()
    monkeypatch.setattr(revision.op, "alter_column", alter_column)
    create_check_constraint = Mock()
    monkeypatch.setattr(
        revision.op,
        "create_check_constraint",
        create_check_constraint,
    )
    add_column = Mock()
    monkeypatch.setattr(revision.op, "add_column", add_column)
    create_index = Mock()
    monkeypatch.setattr(revision.op, "create_index", create_index)
    monkeypatch.setattr(revision.op, "f", lambda name: name)

    revision.upgrade()

    drop_constraint.assert_not_called()
    alter_column.assert_called_once()
    create_check_constraint.assert_called_once_with(
        "ck_quotations_status_allowed",
        "quotations",
        "status IN ('pending','won','lost','cancelled')",
    )
    add_column.assert_called_once()
    create_index.assert_called_once_with(
        "ix_quotations_tenant_deleted_created",
        "quotations",
        ["tenant_id", "deleted_at", "created_at"],
    )
