from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import Mock

import sqlalchemy as sa

import app.models  # noqa: F401
from app.db.base import Base

BACKEND_ROOT = Path(__file__).resolve().parents[2]
OAUTH_REVISION_FILE = (
    BACKEND_ROOT
    / "alembic"
    / "versions"
    / "20260804_0012_feishu_oauth_binding.py"
)
ENTERPRISE_REVISION_FILE = (
    BACKEND_ROOT
    / "alembic"
    / "versions"
    / "20260804_0011_feishu_enterprise_connector.py"
)


def _load_revision():
    spec = importlib.util.spec_from_file_location(
        "feishu_oauth_binding_revision",
        OAUTH_REVISION_FILE,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _install_inspector(
    monkeypatch,
    *,
    phone_exists: bool,
    table_exists: bool,
    indexes=(),
    oauth_timestamp_default=None,
):
    revision = _load_revision()
    inspector = Mock()
    def columns(table_name: str):
        if table_name == "users":
            return (
                [{"name": "id"}, {"name": "phone"}]
                if phone_exists
                else [{"name": "id"}]
            )
        return [
            {"name": "created_at", "default": oauth_timestamp_default},
            {"name": "updated_at", "default": oauth_timestamp_default},
        ]

    inspector.get_columns.side_effect = columns
    inspector.has_table.return_value = table_exists
    inspector.get_indexes.return_value = [{"name": name} for name in indexes]
    monkeypatch.setattr(revision.op, "get_bind", Mock(return_value=object()))
    monkeypatch.setattr(revision.sa, "inspect", Mock(return_value=inspector))
    operations = {
        name: Mock()
        for name in (
            "add_column",
            "alter_column",
            "create_table",
            "create_index",
            "drop_index",
            "drop_table",
            "drop_column",
        )
    }
    for name, operation in operations.items():
        monkeypatch.setattr(revision.op, name, operation)
    return revision, operations


def test_upgrade_uses_plain_datetime_columns(monkeypatch) -> None:
    revision, operations = _install_inspector(
        monkeypatch,
        phone_exists=False,
        table_exists=False,
    )

    revision.upgrade()

    operations["add_column"].assert_called_once()
    operations["create_table"].assert_called_once()
    columns = {
        item.name: item
        for item in operations["create_table"].call_args.args[1:]
        if isinstance(item, sa.Column)
    }
    assert columns["created_at"].server_default is None
    assert columns["updated_at"].server_default is None
    assert columns["created_at"].nullable is False
    assert columns["updated_at"].nullable is False
    assert operations["create_index"].call_count == 2


def test_upgrade_can_be_repeated_after_partial_or_complete_ddl(monkeypatch) -> None:
    revision, operations = _install_inspector(
        monkeypatch,
        phone_exists=True,
        table_exists=True,
        indexes=(
            "ix_feishu_oauth_states_expires",
            "ix_feishu_oauth_states_user",
        ),
    )

    revision.upgrade()

    operations["add_column"].assert_not_called()
    operations["create_table"].assert_not_called()
    operations["create_index"].assert_not_called()
    operations["alter_column"].assert_not_called()


def test_upgrade_removes_timestamp_defaults_from_preexisting_partial_table(
    monkeypatch,
) -> None:
    revision, operations = _install_inspector(
        monkeypatch,
        phone_exists=True,
        table_exists=True,
        indexes=(
            "ix_feishu_oauth_states_expires",
            "ix_feishu_oauth_states_user",
        ),
        oauth_timestamp_default="CURRENT_TIMESTAMP(6)",
    )

    revision.upgrade()

    assert operations["alter_column"].call_count == 2
    for operation in operations["alter_column"].call_args_list:
        assert operation.kwargs["server_default"] is None
        assert operation.kwargs["existing_nullable"] is False


def test_feishu_migrations_have_no_datetime_current_timestamp_server_default() -> None:
    for path in (ENTERPRISE_REVISION_FILE, OAUTH_REVISION_FILE):
        source = path.read_text(encoding="utf-8")
        assert "server_default=sa.func.current_timestamp()" not in source


def test_oauth_state_timestamps_are_application_managed() -> None:
    table = Base.metadata.tables["feishu_oauth_states"]
    assert table.c.created_at.server_default is None
    assert table.c.updated_at.server_default is None
    assert table.c.created_at.default is not None
    assert table.c.updated_at.default is not None
