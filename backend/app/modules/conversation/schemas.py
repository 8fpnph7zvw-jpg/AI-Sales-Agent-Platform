from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ConversationCreate(BaseModel):
    customer_id: str = Field(min_length=26, max_length=26)
    subject: str | None = Field(default=None, max_length=255)


class ConversationRead(BaseModel):
    id: str
    customer_id: str
    customer_name: str
    channel: str
    status: str
    ai_status: str
    last_message_preview: str | None
    last_message_at: datetime | None
    unread_count: int
    created_at: datetime


class ConversationListResponse(BaseModel):
    data: list[ConversationRead]
    total: int
    limit: int
    offset: int


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


class ConversationMessageListResponse(BaseModel):
    data: list[ConversationMessageResponse]
    total: int
    limit: int
    offset: int
