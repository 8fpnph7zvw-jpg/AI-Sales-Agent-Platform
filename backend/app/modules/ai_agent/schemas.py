from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class AgentChatRequest(BaseModel):
    conversation_id: str = Field(min_length=26, max_length=26)
    query: str = Field(min_length=1, max_length=20_000)
    idempotency_key: str = Field(min_length=8, max_length=255)
    inputs: dict[str, Any] = Field(default_factory=dict)


class AgentUsage(BaseModel):
    prompt_tokens: int | None
    completion_tokens: int | None
    cost_amount: Decimal | None
    cost_currency: str | None
    latency_ms: int | None


class AgentChatResponse(BaseModel):
    run_id: str
    conversation_id: str
    message_id: str
    answer: str
    dify_conversation_id: str | None
    citations: list[dict[str, Any]]
    usage: AgentUsage
    duplicate: bool = False
