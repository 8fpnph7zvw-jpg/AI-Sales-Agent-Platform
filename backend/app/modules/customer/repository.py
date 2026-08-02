from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth.role import Role
from app.models.auth.user import User
from app.models.auth.user_role import UserRole
from app.models.customer.customer import Customer


class CustomerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(
        self,
        tenant_id: int,
        *,
        limit: int,
        offset: int,
        search: str | None,
        lifecycle_stage: str | None,
        owner_user_id: int | None,
    ) -> tuple[list[Customer], int]:
        filters = [
            Customer.tenant_id == tenant_id,
            Customer.deleted_at.is_(None),
        ]
        if search:
            pattern = f"%{search.strip()}%"
            filters.append(
                or_(
                    Customer.name.like(pattern),
                    Customer.company_name.like(pattern),
                    Customer.email.like(pattern),
                    Customer.phone_e164.like(pattern),
                )
            )
        if lifecycle_stage:
            filters.append(Customer.lifecycle_stage == lifecycle_stage)
        if owner_user_id is not None:
            filters.append(Customer.owner_user_id == owner_user_id)

        items_statement = (
            select(Customer)
            .where(*filters)
            .order_by(Customer.created_at.desc(), Customer.id.desc())
            .limit(limit)
            .offset(offset)
        )
        count_statement = select(func.count(Customer.id)).where(*filters)
        customers = list((await self.session.scalars(items_statement)).all())
        total = int((await self.session.scalar(count_statement)) or 0)
        return customers, total

    async def get_by_public_id(
        self,
        tenant_id: int,
        public_id: str,
        *,
        for_update: bool = False,
    ) -> Customer | None:
        statement = select(Customer).where(
            Customer.tenant_id == tenant_id,
            Customer.public_id == public_id,
            Customer.deleted_at.is_(None),
        )
        if for_update:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    def add(self, customer: Customer) -> None:
        self.session.add(customer)

    async def get_sales_user(self, tenant_id: int, public_id: str) -> User | None:
        return await self.session.scalar(
            select(User)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(
                User.tenant_id == tenant_id,
                User.public_id == public_id,
                User.status == "active",
                User.deleted_at.is_(None),
                Role.code == "sales",
            )
        )
