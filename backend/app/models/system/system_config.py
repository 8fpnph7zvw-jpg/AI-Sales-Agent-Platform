from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import (
    BIGINT_UNSIGNED,
    Base,
    BigIntPrimaryKeyMixin,
    TimestampMixin,
    VersionMixin,
)


class SystemConfig(
    BigIntPrimaryKeyMixin,
    TimestampMixin,
    VersionMixin,
    Base,
):
    __tablename__ = "system_configs"
    __table_args__ = (UniqueConstraint("tenant_id", "config_key", name="tenant_key"),)

    tenant_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    config_key: Mapped[str] = mapped_column(String(160), nullable=False)
    value_json: Mapped[dict[str, Any] | list[Any] | str | int | bool | None] = mapped_column(JSON)
    value_encrypted: Mapped[bytes | None] = mapped_column(mysql.MEDIUMBLOB)
    is_secret: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    description: Mapped[str | None] = mapped_column(String(500))
    updated_by: Mapped[int | None] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("users.id", ondelete="SET NULL"),
    )
