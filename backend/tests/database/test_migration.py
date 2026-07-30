from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REVISION_FILE = BACKEND_ROOT / "alembic" / "versions" / "20260724_0001_initial_schema.py"


def _load_revision():
    spec = importlib.util.spec_from_file_location("initial_schema_revision", REVISION_FILE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_alembic_has_one_linear_head() -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    scripts = ScriptDirectory.from_config(config)
    assert scripts.get_heads() == ["20260730_0007"]
    assert scripts.get_base() == "20260724_0001"


def test_baseline_sql_files_exist_and_split_into_statements() -> None:
    revision = _load_revision()
    schema = revision.DATABASE_INIT / "001_schema.sql"
    permissions = revision.DATABASE_INIT / "002_permissions_seed.sql"

    schema_statements = list(revision._statements(schema))
    permission_statements = list(revision._statements(permissions))

    assert len([item for item in schema_statements if item.startswith("CREATE TABLE")]) == 31
    assert len(permission_statements) == 1
    assert permission_statements[0].startswith("INSERT INTO permissions")
