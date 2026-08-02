from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth.sales_profile import SalesProfile
from app.models.conversation.message import Message
from app.models.customer.customer import Customer
from app.models.customer.customer_score import CustomerScore


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

    def add_score(self, score: CustomerScore) -> None:
        self.session.add(score)
