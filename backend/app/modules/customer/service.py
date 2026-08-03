from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import Principal
from app.core.exceptions import ResourceNotFoundError
from app.models.conversation.conversation import Conversation
from app.models.customer.customer import Customer
from app.modules.customer.repository import CustomerRepository
from app.modules.customer.schemas import CustomerCreate, CustomerOwnerUpdate, CustomerUpdate


class CustomerService:
    def __init__(
        self,
        session: AsyncSession,
        repository: CustomerRepository,
    ) -> None:
        self.session = session
        self.repository = repository

    async def list_customers(
        self,
        principal: Principal,
        *,
        limit: int,
        offset: int,
        search: str | None,
        lifecycle_stage: str | None,
        category: str | None,
    ) -> tuple[list[Customer], int]:
        return await self.repository.list(
            principal.tenant_id,
            limit=limit,
            offset=offset,
            search=search,
            lifecycle_stage=lifecycle_stage,
            category=category,
            owner_user_id=(
                None if "customer.read_all" in principal.permissions else principal.user_id
            ),
        )

    async def create_customer(
        self,
        principal: Principal,
        payload: CustomerCreate,
    ) -> Customer:
        customer = Customer(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            owner_user_id=principal.user_id,
            **payload.model_dump(),
        )
        self.repository.add(customer)
        await self.session.commit()
        await self.session.refresh(customer)
        return customer

    async def get_customer(self, principal: Principal, customer_id: str) -> Customer:
        customer = await self.repository.get_by_public_id(
            principal.tenant_id,
            customer_id,
        )
        self._ensure_visible(principal, customer)
        return customer

    async def update_customer(
        self,
        principal: Principal,
        customer_id: str,
        payload: CustomerUpdate,
    ) -> Customer:
        customer = await self.repository.get_by_public_id(
            principal.tenant_id,
            customer_id,
            for_update=True,
        )
        self._ensure_visible(principal, customer, update=True)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(customer, field, value)
        await self.session.commit()
        await self.session.refresh(customer)
        return customer

    async def delete_customer(self, principal: Principal, customer_id: str) -> None:
        customer = await self.repository.get_by_public_id(
            principal.tenant_id,
            customer_id,
            for_update=True,
        )
        if customer is None:
            raise ResourceNotFoundError("Customer")
        customer.deleted_at = datetime.now(UTC)
        await self.session.commit()

    async def assign_owner(
        self,
        principal: Principal,
        customer_id: str,
        payload: CustomerOwnerUpdate,
    ) -> Customer:
        customer = await self.repository.get_by_public_id(
            principal.tenant_id,
            customer_id,
            for_update=True,
        )
        if customer is None:
            raise ResourceNotFoundError("Customer")
        if payload.owner_id is None:
            customer.owner_user_id = None
        else:
            owner = await self.repository.get_sales_user(principal.tenant_id, payload.owner_id)
            if owner is None:
                raise ResourceNotFoundError("Sales user")
            customer.owner_user_id = owner.id
        conversations = await self.session.scalars(
            select(Conversation).where(Conversation.customer_id == customer.id)
        )
        for conversation in conversations:
            conversation.assigned_user_id = customer.owner_user_id
        await self.session.commit()
        await self.session.refresh(customer)
        return customer

    @staticmethod
    def _ensure_visible(
        principal: Principal,
        customer: Customer | None,
        *,
        update: bool = False,
    ) -> None:
        if customer is None:
            raise ResourceNotFoundError("Customer")
        all_permission = "customer.update_all" if update else "customer.read_all"
        if (
            all_permission not in principal.permissions
            and customer.owner_user_id != principal.user_id
        ):
            raise ResourceNotFoundError("Customer")
