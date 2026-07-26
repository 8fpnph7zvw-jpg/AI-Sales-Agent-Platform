from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateIndex, CreateTable

import app.models  # noqa: F401
from app.db.base import Base

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_SQL = REPOSITORY_ROOT / "database" / "init" / "001_schema.sql"
CREATE_TABLE_PATTERN = re.compile(
    r"CREATE TABLE\s+([a-z][a-z0-9_]*)\s*\((.*?)\)\s*ENGINE=",
    re.DOTALL,
)
COLUMN_PATTERN = re.compile(r"^    ([a-z][a-z0-9_]*)\s+[A-Z]", re.MULTILINE)
IDENTIFIER_PATTERN = re.compile(r"\b(?:CONSTRAINT|INDEX)\s+([a-z][a-z0-9_]*)")


def _sql_tables() -> dict[str, str]:
    sql = SCHEMA_SQL.read_text(encoding="utf-8")
    return dict(CREATE_TABLE_PATTERN.findall(sql))


def test_schema_sql_and_orm_contain_the_same_tables() -> None:
    assert set(_sql_tables()) == set(Base.metadata.tables)
    assert len(Base.metadata.tables) == 30


def test_schema_sql_and_orm_contain_the_same_columns() -> None:
    sql_tables = _sql_tables()
    for table_name, table in Base.metadata.tables.items():
        sql_columns = set(COLUMN_PATTERN.findall(sql_tables[table_name]))
        model_columns = set(table.columns.keys())
        assert sql_columns == model_columns, table_name


def test_every_model_compiles_for_mysql() -> None:
    dialect = mysql.dialect()
    for table in Base.metadata.sorted_tables:
        ddl = str(CreateTable(table).compile(dialect=dialect))
        assert f"CREATE TABLE {table.name}" in ddl
        for index in table.indexes:
            assert "CREATE INDEX" in str(CreateIndex(index).compile(dialect=dialect))


def test_mysql_identifiers_do_not_exceed_64_characters() -> None:
    schema = SCHEMA_SQL.read_text(encoding="utf-8")
    sql_identifiers = IDENTIFIER_PATTERN.findall(schema)
    assert sql_identifiers
    assert max(map(len, sql_identifiers)) <= 64

    metadata_identifiers = [
        item.name
        for table in Base.metadata.tables.values()
        for item in (*table.constraints, *table.indexes)
        if item.name
    ]
    assert max(map(len, metadata_identifiers)) <= 64


def test_foreign_key_integer_types_are_unsigned() -> None:
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if column.foreign_keys and isinstance(column.type, mysql.BIGINT):
                assert column.type.unsigned is True, f"{table.name}.{column.name}"


def test_all_tenant_owned_tables_have_tenant_id() -> None:
    global_tables = {"tenants", "permissions", "user_roles", "role_permissions", "quotation_items"}
    for table_name, table in Base.metadata.tables.items():
        if table_name not in global_tables:
            assert "tenant_id" in table.columns, table_name
