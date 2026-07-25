from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ConversationMessageCreate(BaseModel):
    conversation_id: str = Field(min_length=26, max_length=26)
    content: str = Field(min_length=1, max_length=20_000)
    message_type: str = Field(default="text", max_length=32)
    idempotency_key: str = Field(min_length=8, max_length=255)
    content_json: dict[str, Any] | None = None


class ConversationMessageResponse(BaseModel):
    id: str
    conversation_id: str
    sequence_no: int
    direction: str
    sender_type: str
    message_type: str
    content: str
    status: str
    duplicate: bool = False
    created_at: datetime
