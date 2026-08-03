from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.api.dependencies.auth import Principal
from app.modules.customer.repository import CustomerRepository
from app.modules.customer.schemas import CustomerUpdate
from app.modules.customer.service import CustomerService

CUSTOMER_PUBLIC_ID = "01KYXZV0FCW81RXQ70Q2ATB3GV"


def principal(*permissions: str) -> Principal:
    return Principal(
        user_id=7,
        user_public_id="01ARZ3NDEKTSV4RRFFQ69G5FA1",
        tenant_id=3,
        tenant_public_id="01ARZ3NDEKTSV4RRFFQ69G5FA2",
        permissions=frozenset(permissions),
    )


@pytest.mark.asyncio
async def test_update_customer_looks_up_public_id() -> None:
    session = AsyncMock()
    repository = AsyncMock()
    customer = SimpleNamespace(owner_user_id=7, lifecycle_stage="new", tags=[])
    repository.get_by_public_id.return_value = customer
    service = CustomerService(session, repository)

    result = await service.update_customer(
        principal("customer.update_own"),
        CUSTOMER_PUBLIC_ID,
        CustomerUpdate(lifecycle_stage="qualified", tags=["high-intent"]),
    )

    repository.get_by_public_id.assert_awaited_once_with(
        3,
        CUSTOMER_PUBLIC_ID,
        for_update=True,
    )
    assert result.lifecycle_stage == "qualified"
    assert result.tags == ["high-intent"]
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_customer_soft_deletes_by_public_id() -> None:
    session = AsyncMock()
    repository = AsyncMock()
    customer = SimpleNamespace(deleted_at=None)
    repository.get_by_public_id.return_value = customer
    service = CustomerService(session, repository)

    await service.delete_customer(
        principal("customer.delete"),
        CUSTOMER_PUBLIC_ID,
    )

    repository.get_by_public_id.assert_awaited_once_with(
        3,
        CUSTOMER_PUBLIC_ID,
        for_update=True,
    )
    assert customer.deleted_at is not None
    session.commit.assert_awaited_once()


class EmptyScalars:
    def all(self) -> list[Any]:
        return []


class CapturingSession:
    def __init__(self) -> None:
        self.statements: list[Any] = []

    async def scalars(self, statement: Any) -> EmptyScalars:
        self.statements.append(statement)
        return EmptyScalars()

    async def scalar(self, statement: Any) -> int:
        self.statements.append(statement)
        return 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "category",
    ["potential", "follow_up", "quoted", "customer", "vip"],
)
async def test_customer_category_filter_uses_json_tag(category: str) -> None:
    session = CapturingSession()
    repository = CustomerRepository(session)  # type: ignore[arg-type]

    customers, total = await repository.list(
        3,
        limit=20,
        offset=0,
        search=None,
        lifecycle_stage=None,
        category=category,
        owner_user_id=None,
    )

    assert customers == []
    assert total == 0
    assert len(session.statements) == 2
    for statement in session.statements:
        assert "json_contains(customers.tags" in str(statement)
        assert f'"customer-category:{category}"' in statement.compile().params.values()
