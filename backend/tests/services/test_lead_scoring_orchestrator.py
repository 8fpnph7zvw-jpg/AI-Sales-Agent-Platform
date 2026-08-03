from __future__ import annotations

import logging
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from app.connectors.whatsapp.service import WhatsAppService
from app.core.config import Settings
from app.models.customer.customer import Customer
from app.services.dify_scoring_service import DifyScoreOutput
from app.services.lead_scoring_orchestrator import LeadScoringOrchestrator


class FakeSession:
    def __init__(self) -> None:
        self.commit_count = 0
        self.refreshed: Any = None

    async def commit(self) -> None:
        self.commit_count += 1

    async def refresh(self, instance: Any) -> None:
        self.refreshed = instance


class FakeRepository:
    def __init__(self) -> None:
        self.scores: list[Any] = []

    async def recent_messages(self, tenant_id: int, customer_id: int) -> list[Any]:
        assert tenant_id == 1
        assert customer_id == 42
        return [SimpleNamespace(sender_type="customer", content_text="Need 1000 jackets")]

    def add_score(self, score: Any) -> None:
        self.scores.append(score)

    async def sales_profile(self, tenant_id: int, user_id: int) -> None:
        raise AssertionError(f"Unexpected sales profile lookup: {tenant_id=} {user_id=}")


class FakeDifyScoring:
    configured = True

    def __init__(self, score: int) -> None:
        self.score = score

    async def run(self, _scoring_input: Any) -> DifyScoreOutput:
        return DifyScoreOutput(
            score=self.score,
            level="A",
            need_follow=False,
            reason="Scored by workflow",
        )


class FakeFeishu:
    async def send_message(self, *_args: Any) -> None:
        raise AssertionError("Feishu notification should not be sent")


def make_customer() -> Customer:
    return Customer(
        id=42,
        public_id="01J00000000000000000000000",
        tenant_id=1,
        name="Test Customer",
        phone_e164="+15550001111",
        tags=[
            "whatsapp",
            "customer-category:旧分类",
            "vip",
            "customer-category:重复分类",
        ],
        owner_user_id=None,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("score", "expected_level", "expected_category"),
    [
        (100, "A", "高意向客户"),
        (70, "A", "高意向客户"),
        (69, "B", "重点跟进"),
        (31, "B", "重点跟进"),
        (30, "C", "潜在客户"),
        (0, "C", "潜在客户"),
    ],
)
async def test_successful_score_replaces_customer_category_tag(
    score: int,
    expected_level: str,
    expected_category: str,
) -> None:
    session = FakeSession()
    repository = FakeRepository()
    customer = make_customer()
    orchestrator = LeadScoringOrchestrator(
        session,  # type: ignore[arg-type]
        repository,  # type: ignore[arg-type]
        FakeDifyScoring(score),  # type: ignore[arg-type]
        FakeFeishu(),  # type: ignore[arg-type]
    )

    result = await orchestrator.score_customer(customer)

    assert customer.tags == [
        "whatsapp",
        "vip",
        f"customer-category:{expected_category}",
    ]
    assert customer.intent_score == Decimal(score)
    assert customer.intent_level == expected_level
    assert result is repository.scores[0]
    assert session.commit_count == 1
    assert session.refreshed is result


class FailingLeadScoring:
    dify = SimpleNamespace(configured=True)

    async def score_customer(self, _customer: Customer) -> None:
        raise RuntimeError("workflow unavailable")


@pytest.mark.asyncio
async def test_whatsapp_scoring_failure_logs_customer_context(
    caplog: pytest.LogCaptureFixture,
) -> None:
    customer = make_customer()
    service = WhatsAppService(
        SimpleNamespace(),  # type: ignore[arg-type]
        SimpleNamespace(),  # type: ignore[arg-type]
        Settings(_env_file=None),
        SimpleNamespace(),  # type: ignore[arg-type]
        SimpleNamespace(),  # type: ignore[arg-type]
        FailingLeadScoring(),  # type: ignore[arg-type]
    )
    caplog.set_level(logging.ERROR)

    await service._score_customer_safely(customer)

    assert "customer_id=01J00000000000000000000000" in caplog.text
    assert "phone=+15550001111" in caplog.text
    assert "exception=workflow unavailable" in caplog.text
