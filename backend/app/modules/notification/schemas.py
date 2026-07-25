from __future__ import annotations

from pydantic import BaseModel, Field


class NotificationSendRequest(BaseModel):
    user_id: str | None = Field(default=None, min_length=26, max_length=26)
    type: str = Field(min_length=1, max_length=64)
    channel: str = Field(min_length=1, max_length=32)
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=20_000)
    resource_type: str | None = Field(default=None, max_length=80)
    resource_id: str | None = Field(default=None, min_length=26, max_length=26)
    priority: str = Field(default="normal", pattern=r"^(low|normal|high|urgent)$")
    dedupe_key: str | None = Field(default=None, min_length=8, max_length=255)


class NotificationSendResponse(BaseModel):
    id: str
    status: str
    channel: str
    queued: bool = True
    duplicate: bool = False
