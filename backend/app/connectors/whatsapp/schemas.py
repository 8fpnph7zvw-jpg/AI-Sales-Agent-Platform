from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class OpenWAContact(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str | None = None
    name: str | None = None
    push_name: str | None = Field(default=None, alias="pushName")


class OpenWAMessageData(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    from_address: str = Field(alias="from")
    to: str | None = None
    body: str | None = None
    type: str = "text"
    timestamp: int | float | str | None = None
    sender_phone: str | None = Field(default=None, alias="senderPhone")
    contact: OpenWAContact | None = None
    has_media: bool = Field(default=False, alias="hasMedia")


class WhatsAppWebhookPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    event: str
    timestamp: datetime | None = None
    session_id: str = Field(alias="sessionId")
    idempotency_key: str = Field(alias="idempotencyKey")
    delivery_id: str = Field(alias="deliveryId")
    data: OpenWAMessageData | dict[str, Any]


class OpenWAStatusWebhookPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    event: str
    timestamp: datetime | None = None
    session_id: str = Field(alias="sessionId")
    delivery_id: str | None = Field(default=None, alias="deliveryId")
    status: str | None = None
    phone_number: str | None = Field(default=None, alias="phoneNumber")
    reason: str | None = None


class WhatsAppInboundMessage(BaseModel):
    message_id: str
    session_id: str
    from_number: str
    to_number: str | None
    display_name: str | None
    message_type: str
    text: str
    occurred_at: datetime
    provider_content: dict[str, Any]


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
    message_id: str = Field(alias="messageId")
    timestamp: int | float | str | None = None


class WhatsAppTestRequest(BaseModel):
    connector_id: str = Field(min_length=26, max_length=26)


class WhatsAppTestResponse(BaseModel):
    connector_id: str
    status: str
    message: str
    latency_ms: int | None
    checked_at: datetime


class OpenWASessionStatusResponse(BaseModel):
    session_id: str | None = None
    name: str | None = None
    status: str
    api_key_configured: bool
    qr_available: bool = False
    phone_number: str | None = None
    last_error: str | None = None
    session_data: dict[str, Any] | None = None


class OpenWAQRCodeResponse(BaseModel):
    session_id: str
    status: str
    data_url: str | None = None
    message: str


class WhatsAppConfigStatusResponse(BaseModel):
    connector_id: str
    configured_keys: list[str]
    required_keys: list[str]
    webhook_url: str


class WhatsAppWebhookResponse(BaseModel):
    status: str = "accepted"
    processed: int = 0
    duplicates: int = 0


def parse_inbound_messages(
    payload: WhatsAppWebhookPayload,
) -> list[WhatsAppInboundMessage]:
    if payload.event != "message.received":
        return []
    message = (
        payload.data
        if isinstance(payload.data, OpenWAMessageData)
        else OpenWAMessageData.model_validate(payload.data)
    )
    sender = message.sender_phone or message.from_address
    display_name = None
    if message.contact is not None:
        display_name = message.contact.name or message.contact.push_name
    return [
        WhatsAppInboundMessage(
            message_id=message.id,
            session_id=payload.session_id,
            from_number=sender,
            to_number=message.to,
            display_name=display_name,
            message_type=message.type,
            text=_message_text(message),
            occurred_at=_timestamp(message.timestamp),
            provider_content=message.model_dump(by_alias=True, exclude_none=True),
        )
    ]


def normalize_chat_id(value: str) -> str:
    candidate = value.strip()
    if "@" in candidate:
        return candidate
    digits = "".join(character for character in candidate if character.isdigit())
    if not digits:
        return candidate
    return f"{digits}@c.us"


def _timestamp(value: int | float | str | None) -> datetime:
    try:
        if value is None:
            raise ValueError
        return datetime.fromtimestamp(float(value), tz=UTC)
    except (TypeError, ValueError, OverflowError):
        return datetime.now(UTC)


def _message_text(message: OpenWAMessageData) -> str:
    if message.body:
        return message.body
    return f"[WhatsApp {message.type} message]"
