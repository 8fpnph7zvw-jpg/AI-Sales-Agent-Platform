from __future__ import annotations

import os
import time
from datetime import UTC, datetime

from sqlalchemy import MetaData, func
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.db.types import UTCDateTime

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

BIGINT_UNSIGNED = mysql.BIGINT(unsigned=True)
ULID_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_ulid() -> str:
    """Generate a 26-character, time-sortable ULID without an extra dependency."""

    timestamp = int(time.time() * 1000).to_bytes(6, "big")
    value = int.from_bytes(timestamp + os.urandom(10), "big")
    encoded = ["0"] * 26
    for index in range(25, -1, -1):
        encoded[index] = ULID_ALPHABET[value & 31]
        value >>= 5
    return "".join(encoded)


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class BigIntPrimaryKeyMixin:
    id: Mapped[int] = mapped_column(BIGINT_UNSIGNED, primary_key=True, autoincrement=True)


class PublicIdMixin:
    public_id: Mapped[str] = mapped_column(
        mysql.CHAR(26), unique=True, nullable=False, default=new_ulid
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, server_default=func.current_timestamp(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        default=utc_now,
        server_default=func.current_timestamp(),
        onupdate=utc_now,
        nullable=False,
    )


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class VersionMixin:
    version: Mapped[int] = mapped_column(
        mysql.INTEGER(unsigned=True), nullable=False, default=1, server_default="1"
    )
