from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer.customer import Customer


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
