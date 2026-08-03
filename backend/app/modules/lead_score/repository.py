from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth.sales_profile import SalesProfile
from app.models.conversation.message import Message
from app.models.customer.customer import Customer
from app.models.customer.customer_score import CustomerScore
from app.models.quotation.quotation import Quotation


class LeadScoreRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_customer_for_update(
        self,
        tenant_id: int,
        public_id: str,
    ) -> Customer | None:
        statement = (
            select(Customer)
            .where(
                Customer.tenant_id == tenant_id,
                Customer.public_id == public_id,
                Customer.deleted_at.is_(None),
            )
            .with_for_update()
        )
        return await self.session.scalar(statement)

    async def get_customer(
        self,
        tenant_id: int,
        public_id: str,
        *,
        owner_user_id: int | None = None,
        for_update: bool = False,
    ) -> Customer | None:
        statement = select(Customer).where(
            Customer.tenant_id == tenant_id,
            Customer.public_id == public_id,
            Customer.deleted_at.is_(None),
        )
        if owner_user_id is not None:
            statement = statement.where(Customer.owner_user_id == owner_user_id)
        if for_update:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def recent_messages(
        self,
        tenant_id: int,
        customer_id: int,
        *,
        limit: int = 40,
    ) -> list[Message]:
        rows = list(
            (
                await self.session.scalars(
                    select(Message)
                    .join(Message.conversation)
                    .where(
                        Message.tenant_id == tenant_id,
                        Message.conversation.has(customer_id=customer_id),
                    )
                    .order_by(Message.created_at.desc(), Message.id.desc())
                    .limit(limit)
                )
            ).all()
        )
        rows.reverse()
        return rows

    async def sales_profile(self, tenant_id: int, user_id: int) -> SalesProfile | None:
        return await self.session.scalar(
            select(SalesProfile).where(
                SalesProfile.tenant_id == tenant_id,
                SalesProfile.user_id == user_id,
            )
        )

    async def has_won_quotation(self, tenant_id: int, customer_id: int) -> bool:
        return (
            await self.session.scalar(
                select(Quotation.id)
                .where(
                    Quotation.tenant_id == tenant_id,
                    Quotation.customer_id == customer_id,
                    Quotation.status == "won",
                )
                .limit(1)
            )
            is not None
        )

    async def list_scores(
        self,
        tenant_id: int,
        *,
        owner_user_id: int | None,
        customer_public_id: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[tuple[CustomerScore, Customer]], int]:
        filters = [CustomerScore.tenant_id == tenant_id, Customer.deleted_at.is_(None)]
        if owner_user_id is not None:
            filters.append(Customer.owner_user_id == owner_user_id)
        if customer_public_id:
            filters.append(Customer.public_id == customer_public_id)
        base = (
            select(CustomerScore, Customer)
            .join(Customer, Customer.id == CustomerScore.customer_id)
            .where(*filters)
        )
        rows = list(
            (
                await self.session.execute(
                    base.order_by(CustomerScore.created_time.desc(), CustomerScore.id.desc())
                    .limit(limit)
                    .offset(offset)
                )
            ).tuples()
        )
        total = int(
            (
                await self.session.scalar(
                    select(func.count(CustomerScore.id)).join(Customer).where(*filters)
                )
            )
            or 0
        )
        return rows, total

    async def list_current_scores(
        self,
        tenant_id: int,
        *,
        owner_user_id: int | None,
        customer_public_id: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[tuple[Customer, datetime | None]], int]:
        latest_score = (
            select(
                CustomerScore.customer_id,
                func.max(CustomerScore.created_time).label("last_scored_at"),
            )
            .where(CustomerScore.tenant_id == tenant_id)
            .group_by(CustomerScore.customer_id)
            .subquery()
        )
        filters = [
            Customer.tenant_id == tenant_id,
            Customer.deleted_at.is_(None),
            Customer.intent_score.is_not(None),
        ]
        if owner_user_id is not None:
            filters.append(Customer.owner_user_id == owner_user_id)
        if customer_public_id:
            filters.append(Customer.public_id == customer_public_id)
        base = (
            select(Customer, latest_score.c.last_scored_at)
            .outerjoin(latest_score, latest_score.c.customer_id == Customer.id)
            .where(*filters)
        )
        rows = list(
            (
                await self.session.execute(
                    base.order_by(
                        latest_score.c.last_scored_at.desc(),
                        Customer.updated_at.desc(),
                        Customer.id.desc(),
                    )
                    .limit(limit)
                    .offset(offset)
                )
            ).tuples()
        )
        total = int(
            (
                await self.session.scalar(
                    select(func.count(Customer.id))
                    .outerjoin(latest_score, latest_score.c.customer_id == Customer.id)
                    .where(*filters)
                )
            )
            or 0
        )
        return rows, total

    async def get_score_for_customer(
        self,
        tenant_id: int,
        customer_public_id: str,
        score_id: int,
        *,
        owner_user_id: int | None,
    ) -> CustomerScore | None:
        statement = (
            select(CustomerScore)
            .join(Customer, Customer.id == CustomerScore.customer_id)
            .where(
                CustomerScore.id == score_id,
                CustomerScore.tenant_id == tenant_id,
                Customer.public_id == customer_public_id,
                Customer.deleted_at.is_(None),
            )
        )
        if owner_user_id is not None:
            statement = statement.where(Customer.owner_user_id == owner_user_id)
        return await self.session.scalar(statement)

    def add_score(self, score: CustomerScore) -> None:
        self.session.add(score)
