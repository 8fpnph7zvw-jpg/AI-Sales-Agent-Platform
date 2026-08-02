from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.api.dependencies.auth import Principal
from app.integrations.dify.client import DifyChatResult
from app.modules.ai_agent.schemas import AgentChatRequest, AgentChatResponse, AgentUsage
from app.modules.ai_agent.service import AiAgentService


class FakeSession:
    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        return None


class FakeRepository:
    def __init__(self) -> None:
        self.conversation = SimpleNamespace(
            id=7,
            public_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
            ai_enabled=True,
            mode="ai",
            status="open",
        )
        self.added: list[Any] = []

    async def get_conversation_for_update(
        self, tenant_id: int, public_id: str
    ) -> tuple[SimpleNamespace, str, int]:
        assert tenant_id == 1
        assert public_id == self.conversation.public_id
        return self.conversation, "01ARZ3NDEKTSV4RRFFQ69G5FAW", 9

    async def get_message_by_idempotency(
        self, tenant_id: int, idempotency_key: str
    ) -> None:
        assert tenant_id == 1
        assert idempotency_key == "request-key-1"
        return None

    async def next_sequence(self, conversation_id: int) -> int:
        assert conversation_id == 7
        return 1

    def add(self, entity: Any) -> None:
        if getattr(entity, "id", None) is None:
            entity.id = len(self.added) + 1
        if getattr(entity, "public_id", None) is None:
            entity.public_id = f"test-public-{len(self.added) + 1}"
        self.added.append(entity)

    async def latest_dify_conversation_id(self, conversation_id: int) -> str:
        assert conversation_id == 7
        return "dify-existing-conversation"


class FakeDify:
    def __init__(self) -> None:
        self.kwargs: dict[str, Any] = {}

    async def chat(self, **kwargs: Any) -> DifyChatResult:
        self.kwargs = kwargs
        return DifyChatResult(
            answer="continued answer",
            conversation_id="dify-existing-conversation",
            task_id="dify-task",
            message_id="dify-message",
            retry_count=0,
        )


@pytest.mark.asyncio
async def test_ai_agent_chat_reuses_latest_dify_conversation_id() -> None:
    repository = FakeRepository()
    dify = FakeDify()
    service = AiAgentService(FakeSession(), repository, dify)
    expected = AgentChatResponse(
        run_id="run-public-id",
        conversation_id=repository.conversation.public_id,
        message_id="message-public-id",
        answer="continued answer",
        dify_conversation_id="dify-existing-conversation",
        citations=[],
        usage=AgentUsage(
            prompt_tokens=None,
            completion_tokens=None,
            cost_amount=Decimal("0"),
            cost_currency=None,
            latency_ms=None,
        ),
    )
    service._complete_run = AsyncMock(return_value=expected)  # type: ignore[method-assign]

    response = await service.chat(
        Principal(
            user_id=5,
            user_public_id="user-public-id",
            tenant_id=1,
            tenant_public_id="tenant-public-id",
            permissions=frozenset({"ai_agent.chat"}),
        ),
        AgentChatRequest(
            conversation_id=repository.conversation.public_id,
            query="1000 units USA",
            idempotency_key="request-key-1",
        ),
    )

    assert response == expected
    assert dify.kwargs["conversation_id"] == "dify-existing-conversation"
