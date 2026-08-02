from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BIGINT_UNSIGNED, Base, BigIntPrimaryKeyMixin
from app.db.types import UTCDateTime


class CustomerScore(BigIntPrimaryKeyMixin, Base):
    __tablename__ = "customer_scores"
    __table_args__ = (
        CheckConstraint("score >= 0 AND score <= 100", name="score_range"),
        CheckConstraint("level IN ('A','B','C','D')", name="level_allowed"),
        Index("ix_customer_scores_customer_created", "customer_id", "created_time"),
        Index("ix_customer_scores_tenant_follow", "tenant_id", "need_follow", "created_time"),
    )

    tenant_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    customer_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED,
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
    )
    score: Mapped[int] = mapped_column(mysql.TINYINT(unsigned=True), nullable=False)
    level: Mapped[str] = mapped_column(String(1), nullable=False)
    need_follow: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_time: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        server_default=func.current_timestamp(),
    )

    customer = relationship("Customer", back_populates="scores")
