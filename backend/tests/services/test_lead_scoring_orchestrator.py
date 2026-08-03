from __future__ import annotations

import logging
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, call

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
    def __init__(
        self,
        *,
        has_won_history: bool = False,
        customer_message: str = "How much this hat?",
    ) -> None:
        self.scores: list[Any] = []
        self.has_won_history = has_won_history
        self.customer_message = customer_message

    async def recent_messages(self, tenant_id: int, customer_id: int) -> list[Any]:
        assert tenant_id == 1
        assert customer_id == 42
        return [
            SimpleNamespace(sender_type="customer", content_text=self.customer_message),
            SimpleNamespace(
                sender_type="ai",
                content_text=(
                    "Please provide 1000 pcs hats, ship to USA, and request a quotation."
                ),
            ),
        ]

    def add_score(self, score: Any) -> None:
        self.scores.append(score)

    async def sales_profile(self, tenant_id: int, user_id: int) -> None:
        raise AssertionError(f"Unexpected sales profile lookup: {tenant_id=} {user_id=}")

    async def has_won_quotation(self, tenant_id: int, customer_id: int) -> bool:
        assert tenant_id == 1
        assert customer_id == 42
        return self.has_won_history


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


class FollowUpDifyScoring:
    configured = True

    async def run(self, _scoring_input: Any) -> DifyScoreOutput:
        return DifyScoreOutput(
            score=85,
            level="A",
            need_follow=True,
            reason="Complete purchasing context",
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
    ("score", "expected_level"),
    [
        (100, "A"),
        (70, "A"),
        (69, "B"),
        (31, "B"),
        (30, "C"),
        (0, "C"),
    ],
)
async def test_successful_score_updates_intent_without_promoting_incomplete_customer(
    score: int,
    expected_level: str,
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
        "customer-category:potential",
    ]
    assert customer.intent_score == Decimal(score)
    assert customer.intent_level == expected_level
    assert result is repository.scores[0]
    assert session.commit_count == 1
    assert session.refreshed is result


@pytest.mark.asyncio
async def test_score_customer_triggers_customer_category_service(
    caplog: pytest.LogCaptureFixture,
) -> None:
    session = FakeSession()
    repository = FakeRepository()
    customer = make_customer()
    orchestrator = LeadScoringOrchestrator(
        session,  # type: ignore[arg-type]
        repository,  # type: ignore[arg-type]
        FollowUpDifyScoring(),  # type: ignore[arg-type]
        FakeFeishu(),  # type: ignore[arg-type]
    )
    category_service = Mock()
    category_service.get_customer_category.return_value = "potential"
    category_service.update_customer_category.return_value = "potential"
    orchestrator.customer_category = category_service
    caplog.set_level(logging.INFO)

    await orchestrator.score_customer(customer)

    assert call(
        customer,
        source="scoring",
        conversation_history="How much this hat?",
    ) in category_service.update_customer_category.call_args_list
    assert customer.intent_score == Decimal(85)
    assert customer.intent_level == "A"
    assert "category_update_started customer_id=42 score=85 level=A need_follow=True" in caplog.text
    assert "conversation_history=How much this hat?" in caplog.text
    assert "customer_requested_quote=False" in caplog.text
    assert "category_update_finished customer_id=42 old_category=potential " in caplog.text
    assert "new_category=potential" in caplog.text
    assert "missing_fields=quantity,country,shipping_method,customer_requested_quote" in caplog.text


@pytest.mark.asyncio
async def test_complete_context_updates_category_after_scoring(
    caplog: pytest.LogCaptureFixture,
) -> None:
    session = FakeSession()
    repository = FakeRepository(
        customer_message="Need 1000 hats. Ship to USA. By sea. Please quote."
    )
    customer = make_customer()
    orchestrator = LeadScoringOrchestrator(
        session,  # type: ignore[arg-type]
        repository,  # type: ignore[arg-type]
        FollowUpDifyScoring(),  # type: ignore[arg-type]
        FakeFeishu(),  # type: ignore[arg-type]
    )
    caplog.set_level(logging.INFO)

    await orchestrator.score_customer(customer)

    assert customer.tags == ["whatsapp", "vip", "customer-category:follow_up"]
    assert "category_update_finished customer_id=42" in caplog.text
    assert "new_category=follow_up" in caplog.text
    assert "missing_fields=none" in caplog.text


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
