from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from app.api.dependencies.auth import Principal
from app.models.customer.customer import Customer
from app.models.customer.customer_score import CustomerScore
from app.modules.lead_score.repository import LeadScoreRepository
from app.modules.lead_score.service import LeadScoreService


def test_lead_score_levels_are_stable() -> None:
    assert LeadScoreService._level(80) == "hot"
    assert LeadScoreService._level(60) == "warm"
    assert LeadScoreService._level(40) == "nurture"
    assert LeadScoreService._level(39.99) == "cold"


def make_principal() -> Principal:
    return Principal(
        user_id=7,
        user_public_id="01J00000000000000000000007",
        tenant_id=1,
        tenant_public_id="01J00000000000000000000001",
        permissions=frozenset({"customer.score", "customer.read_all"}),
    )


def make_customer() -> Customer:
    return Customer(
        id=42,
        public_id="01J00000000000000000000042",
        tenant_id=1,
        name="Current Score Customer",
        lifecycle_stage="new",
        intent_score=Decimal("85"),
        intent_level="A",
        tags=["whatsapp", "customer-category:follow_up"],
    )


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


@pytest.mark.asyncio
async def test_current_score_query_groups_history_by_customer() -> None:
    session = CapturingSession()
    repository = LeadScoreRepository(session)  # type: ignore[arg-type]

    rows, total = await repository.list_current_scores(
        1,
        owner_user_id=None,
        customer_public_id=None,
        limit=20,
        offset=0,
    )

    assert rows == []
    assert total == 0
    sql = " ".join(str(statement) for statement in session.statements)
    assert "max(customer_scores.created_time)" in sql
    assert "GROUP BY customer_scores.customer_id" in sql
    assert "customers.intent_score IS NOT NULL" in sql
    assert "LEFT OUTER JOIN" in sql


class FakeRepository:
    def __init__(self, customer: Customer, score: CustomerScore | None = None) -> None:
        self.customer = customer
        self.score = score

    async def list_current_scores(self, *_args: Any, **_kwargs: Any):
        return [(self.customer, datetime(2026, 8, 3, tzinfo=UTC))], 1

    async def get_score_for_customer(self, *_args: Any, **_kwargs: Any):
        return self.score


class FakeSession:
    def __init__(self) -> None:
        self.deleted: list[Any] = []
        self.commit_count = 0

    async def delete(self, instance: Any) -> None:
        self.deleted.append(instance)

    async def commit(self) -> None:
        self.commit_count += 1


@pytest.mark.asyncio
async def test_current_score_list_uses_customer_current_fields() -> None:
    customer = make_customer()
    service = LeadScoreService(
        FakeSession(),  # type: ignore[arg-type]
        FakeRepository(customer),  # type: ignore[arg-type]
    )

    response = await service.list_current_scores(
        make_principal(),
        customer_id=None,
        limit=20,
        offset=0,
    )

    assert response.total == 1
    assert len(response.data) == 1
    assert response.data[0].intent_score == Decimal("85")
    assert response.data[0].intent_level == "A"
    assert response.data[0].category == "follow_up"


@pytest.mark.asyncio
async def test_delete_score_history_deletes_only_customer_score() -> None:
    customer = make_customer()
    score = CustomerScore(
        id=99,
        tenant_id=1,
        customer_id=customer.id,
        score=80,
        level="A",
        need_follow=True,
        reason="Test score",
    )
    session = FakeSession()
    service = LeadScoreService(
        session,  # type: ignore[arg-type]
        FakeRepository(customer, score),  # type: ignore[arg-type]
    )

    await service.delete_score_history(make_principal(), customer.public_id, score.id)

    assert session.deleted == [score]
    assert session.commit_count == 1
    assert customer.name == "Current Score Customer"
