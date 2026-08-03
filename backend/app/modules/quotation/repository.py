from __future__ import annotations

from sqlalchemy import func, select
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

    async def get_quotation_with_customer(
        self,
        tenant_id: int,
        public_id: str,
        *,
        for_update: bool = False,
    ) -> tuple[Quotation, Customer] | None:
        statement = (
            select(Quotation, Customer)
            .join(Customer, Customer.id == Quotation.customer_id)
            .where(
                Quotation.tenant_id == tenant_id,
                Quotation.public_id == public_id,
                Quotation.deleted_at.is_(None),
            )
        )
        if for_update:
            statement = statement.with_for_update()
        row = (await self.session.execute(statement)).one_or_none()
        return (row[0], row[1]) if row else None

    async def has_won_quotation(
        self,
        tenant_id: int,
        customer_id: int,
        *,
        exclude_quotation_id: int | None = None,
    ) -> bool:
        statement = select(Quotation.id).where(
            Quotation.tenant_id == tenant_id,
            Quotation.customer_id == customer_id,
            Quotation.status == "won",
        )
        if exclude_quotation_id is not None:
            statement = statement.where(Quotation.id != exclude_quotation_id)
        return await self.session.scalar(statement.limit(1)) is not None

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

    async def list_quotations(
        self,
        tenant_id: int,
        *,
        limit: int,
        offset: int,
        status: str | None,
        created_by: int | None,
    ) -> tuple[list[tuple[Quotation, Customer]], int]:
        filters = [
            Quotation.tenant_id == tenant_id,
            Quotation.deleted_at.is_(None),
        ]
        if status:
            filters.append(Quotation.status == status)
        if created_by is not None:
            filters.append(Quotation.created_by == created_by)
        base = (
            select(Quotation, Customer)
            .join(Customer, Customer.id == Quotation.customer_id)
            .where(*filters)
        )
        rows = list(
            (
                await self.session.execute(
                    base.order_by(Quotation.created_at.desc(), Quotation.id.desc())
                    .limit(limit)
                    .offset(offset)
                )
            ).tuples()
        )
        total = int(
            (await self.session.scalar(select(func.count(Quotation.id)).where(*filters))) or 0
        )
        return rows, total

    async def list_products(
        self,
        tenant_id: int,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[Product], int]:
        filters = [
            Product.tenant_id == tenant_id,
            Product.deleted_at.is_(None),
            Product.status == "active",
        ]
        products = list(
            (
                await self.session.scalars(
                    select(Product)
                    .where(*filters)
                    .order_by(Product.name, Product.id)
                    .limit(limit)
                    .offset(offset)
                )
            ).all()
        )
        total = int(
            (await self.session.scalar(select(func.count(Product.id)).where(*filters))) or 0
        )
        return products, total
