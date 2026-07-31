from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, Field


class WhatsAppSendRequest(BaseModel):
    recipient: str = Field(
        min_length=5,
        max_length=128,
        validation_alias=AliasChoices("phone", "recipient"),
        serialization_alias="phone",
    )
    text: str = Field(
        min_length=1,
        max_length=4096,
        validation_alias=AliasChoices("message", "text"),
        serialization_alias="message",
    )


class WhatsAppSendResponse(BaseModel):
    message_id: str


class WhatsAppTestRequest(BaseModel):
    connector_id: str = Field(min_length=26, max_length=26)


class WhatsAppTestResponse(BaseModel):
    connector_id: str
    status: str
    message: str
    latency_ms: int | None
    checked_at: datetime


class WhatsAppConfigStatusResponse(BaseModel):
    connector_id: str
    adapter: str
    configured_keys: list[str]
    required_keys: list[str]
    webhook_url: str


class WhatsAppWebhookResponse(BaseModel):
    status: str = "accepted"
    processed: int = 0
    duplicates: int = 0


class WhatsAppProviderPayload(BaseModel):
    """Opaque payload accepted at the provider-neutral webhook boundary."""

    data: dict[str, Any]


class WhatsAppGatewayInboundRequest(BaseModel):
    phone: str = Field(min_length=5, max_length=32)
    message: str = Field(min_length=1, max_length=20_000)
    channel: Literal["whatsapp"] = "whatsapp"
    timestamp: int | float | None = Field(default=None, gt=0)
    message_id: str | None = Field(default=None, min_length=1, max_length=255)
    session_id: str | None = Field(default=None, min_length=1, max_length=64)
    connector_id: str | None = Field(default=None, min_length=26, max_length=26)
