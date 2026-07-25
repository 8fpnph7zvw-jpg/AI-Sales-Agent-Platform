from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import (
    BIGINT_UNSIGNED,
    Base,
    BigIntPrimaryKeyMixin,
    TimestampMixin,
)


class ConnectorConfig(BigIntPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "connector_configs"
    __table_args__ = (UniqueConstraint("connector_id", "config_key", name="connector_key"),)

    tenant_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    connector_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("connectors.id", ondelete="CASCADE"),
        nullable=False,
    )
    config_key: Mapped[str] = mapped_column(String(120), nullable=False)
    value_type: Mapped[str] = mapped_column(
        String(24), nullable=False, default="string", server_default="string"
    )
    value_encrypted: Mapped[bytes | None] = mapped_column(mysql.MEDIUMBLOB)
    secret_ref: Mapped[str | None] = mapped_column(String(512))
    key_version: Mapped[str | None] = mapped_column(String(64))
    is_secret: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    updated_by: Mapped[int | None] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("users.id", ondelete="SET NULL"),
    )

    connector = relationship("Connector", back_populates="configs")
