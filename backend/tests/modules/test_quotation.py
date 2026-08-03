from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from app.api.dependencies.auth import Principal
from app.models.customer.customer import Customer
from app.models.quotation.quotation import Quotation
from app.modules.quotation.repository import QuotationRepository
from app.modules.quotation.schemas import (
    QuotationCreate,
    QuotationItemCreate,
    QuotationStatusUpdate,
)
from app.modules.quotation.service import QuotationService


def test_money_rounds_to_mysql_scale() -> None:
    assert QuotationService._money(Decimal("12.34567")) == Decimal("12.3457")
    assert QuotationService._money(Decimal("12.34565")) == Decimal("12.3457")


class FakeSession:
    def __init__(self) -> None:
        self.commit_count = 0

    async def commit(self) -> None:
        self.commit_count += 1

    async def refresh(self, instance: Any) -> None:
        if getattr(instance, "created_at", None) is None:
            instance.created_at = datetime.now(UTC)


class FakeQuotationRepository:
    def __init__(self, customer: Customer, *, has_won_history: bool = False) -> None:
        self.customer = customer
        self.has_won_history = has_won_history
        self.quotation: Quotation | None = None

    async def get_customer(self, tenant_id: int, public_id: str) -> Customer | None:
        if tenant_id == self.customer.tenant_id and public_id == self.customer.public_id:
            return self.customer
        return None

    async def get_conversation(self, *_args: Any) -> None:
        return None

    async def get_products(self, *_args: Any) -> dict[str, Any]:
        return {}

    async def has_won_quotation(self, *_args: Any, **_kwargs: Any) -> bool:
        return self.has_won_history

    def add(self, quotation: Quotation) -> None:
        quotation.id = 99
        self.quotation = quotation

    async def get_quotation_with_customer(
        self,
        tenant_id: int,
        public_id: str,
        *,
        for_update: bool = False,
    ) -> tuple[Quotation, Customer] | None:
        assert for_update is True
        if (
            self.quotation is not None
            and self.quotation.tenant_id == tenant_id
            and self.quotation.public_id == public_id
            and self.quotation.deleted_at is None
        ):
            return self.quotation, self.customer
        return None


class EmptyRows:
    def tuples(self) -> list[Any]:
        return []


class CapturingSession:
    def __init__(self) -> None:
        self.statements: list[Any] = []

    async def execute(self, statement: Any) -> EmptyRows:
        self.statements.append(statement)
        return EmptyRows()

    async def scalar(self, statement: Any) -> int:
        self.statements.append(statement)
        return 0


def make_principal() -> Principal:
    return Principal(
        user_id=7,
        user_public_id="01J00000000000000000000007",
        tenant_id=1,
        tenant_public_id="01J00000000000000000000001",
        permissions=frozenset({"quotation.create", "quotation.update_own"}),
    )


def make_customer(category: str = "potential") -> Customer:
    return Customer(
        id=42,
        public_id="01J00000000000000000000042",
        tenant_id=1,
        name="Test Customer",
        lifecycle_stage="new",
        owner_user_id=7,
        tags=["whatsapp", f"customer-category:{category}"],
    )


def quotation_payload() -> QuotationCreate:
    return QuotationCreate(
        customer_id="01J00000000000000000000042",
        currency="USD",
        items=[
            QuotationItemCreate(
                sku="HAT-01",
                name="Hat",
                quantity=Decimal("1000"),
                unit="pcs",
                unit_price=Decimal("2.50"),
            )
        ],
    )


@pytest.mark.asyncio
async def test_create_quotation_defaults_pending_and_marks_customer_quoted() -> None:
    customer = make_customer()
    repository = FakeQuotationRepository(customer)
    session = FakeSession()
    service = QuotationService(session, repository)  # type: ignore[arg-type]

    response = await service.create(make_principal(), quotation_payload())

    assert response.status == "pending"
    assert repository.quotation is not None
    assert repository.quotation.status == "pending"
    assert customer.tags == ["whatsapp", "customer-category:quoted"]
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_new_quotation_for_won_customer_marks_customer_vip() -> None:
    customer = make_customer("customer")
    repository = FakeQuotationRepository(customer, has_won_history=True)
    service = QuotationService(FakeSession(), repository)  # type: ignore[arg-type]

    await service.create(make_principal(), quotation_payload())

    assert customer.tags == ["whatsapp", "customer-category:vip"]


@pytest.mark.asyncio
async def test_list_quotations_filters_soft_deleted_rows() -> None:
    session = CapturingSession()
    repository = QuotationRepository(session)  # type: ignore[arg-type]

    rows, total = await repository.list_quotations(
        1,
        limit=20,
        offset=0,
        status=None,
        created_by=None,
    )

    assert rows == []
    assert total == 0
    assert session.statements
    assert all("quotations.deleted_at IS NULL" in str(item) for item in session.statements)


@pytest.mark.asyncio
async def test_first_won_quotation_marks_customer_won() -> None:
    customer = make_customer("quoted")
    quotation = Quotation(
        id=99,
        public_id="01J00000000000000000000099",
        tenant_id=1,
        quotation_no="Q-000000000099",
        customer_id=customer.id,
        status="pending",
        currency="USD",
        created_by=7,
        deleted_at=None,
    )
    repository = FakeQuotationRepository(customer)
    repository.quotation = quotation
    service = QuotationService(FakeSession(), repository)  # type: ignore[arg-type]

    response = await service.update_status(
        make_principal(),
        quotation.public_id,
        QuotationStatusUpdate(status="won"),
    )

    assert response.status == "won"
    assert customer.tags == ["whatsapp", "customer-category:customer"]


@pytest.mark.asyncio
async def test_soft_delete_preserves_customer_and_category() -> None:
    customer = make_customer("customer")
    quotation = Quotation(
        id=99,
        public_id="01J00000000000000000000099",
        tenant_id=1,
        quotation_no="Q-000000000099",
        customer_id=customer.id,
        status="won",
        currency="USD",
        created_by=7,
        deleted_at=None,
    )
    repository = FakeQuotationRepository(customer)
    repository.quotation = quotation
    service = QuotationService(FakeSession(), repository)  # type: ignore[arg-type]

    await service.delete(make_principal(), quotation.public_id)

    assert quotation.deleted_at is not None
    assert quotation.status == "won"
    assert customer.tags == ["whatsapp", "customer-category:customer"]
