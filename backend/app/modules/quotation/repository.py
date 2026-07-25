from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation.conversation import Conversation
from app.models.customer.customer import Customer
from app.models.quotation.product import Product
from app.models.quotation.quotation import Quotation


class QuotationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_customer(self, tenant_id: int, public_id: str) -> Customer | None:
        statement = select(Customer).where(
            Customer.tenant_id == tenant_id,
            Customer.public_id == public_id,
            Customer.deleted_at.is_(None),
        )
        return await self.session.scalar(statement)

    async def get_conversation(
        self,
        tenant_id: int,
        public_id: str,
    ) -> Conversation | None:
        statement = select(Conversation).where(
            Conversation.tenant_id == tenant_id,
            Conversation.public_id == public_id,
        )
        return await self.session.scalar(statement)

    async def get_products(
        self,
        tenant_id: int,
        public_ids: set[str],
    ) -> dict[str, Product]:
        if not public_ids:
            return {}
        statement = select(Product).where(
            Product.tenant_id == tenant_id,
            Product.public_id.in_(public_ids),
            Product.deleted_at.is_(None),
            Product.status == "active",
        )
        products = (await self.session.scalars(statement)).all()
        return {product.public_id: product for product in products}

    def add(self, quotation: Quotation) -> None:
        self.session.add(quotation)
