from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WhatsAppText(BaseModel):
    body: str = Field(min_length=1, max_length=20_000)


class WhatsAppProfile(BaseModel):
    name: str | None = Field(default=None, max_length=255)


class WhatsAppContact(BaseModel):
    wa_id: str
    profile: WhatsAppProfile | None = None


class WhatsAppMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    from_number: str = Field(alias="from")
    timestamp: str
    type: str
    text: WhatsAppText | None = None
    image: dict[str, Any] | None = None
    document: dict[str, Any] | None = None
    audio: dict[str, Any] | None = None
    video: dict[str, Any] | None = None
    sticker: dict[str, Any] | None = None
    location: dict[str, Any] | None = None
    button: dict[str, Any] | None = None
    interactive: dict[str, Any] | None = None


class WhatsAppMetadata(BaseModel):
    display_phone_number: str | None = None
    phone_number_id: str


class WhatsAppChangeValue(BaseModel):
    model_config = ConfigDict(extra="allow")

    messaging_product: str | None = None
    metadata: WhatsAppMetadata | None = None
    contacts: list[WhatsAppContact] = Field(default_factory=list)
    messages: list[WhatsAppMessage] = Field(default_factory=list)
    statuses: list[dict[str, Any]] = Field(default_factory=list)


class WhatsAppChange(BaseModel):
    field: str
    value: WhatsAppChangeValue


class WhatsAppEntry(BaseModel):
    id: str
    changes: list[WhatsAppChange] = Field(default_factory=list)


class WhatsAppWebhookPayload(BaseModel):
    object: str
    entry: list[WhatsAppEntry] = Field(default_factory=list)

    def phone_number_ids(self) -> set[str]:
        return {
            change.value.metadata.phone_number_id
            for entry in self.entry
            for change in entry.changes
            if change.value.metadata is not None
        }


class WhatsAppInboundMessage(BaseModel):
    message_id: str
    phone_number_id: str
    from_number: str
    display_name: str | None
    message_type: str
    text: str
    occurred_at: datetime
    provider_content: dict[str, Any]


class WhatsAppSendResponse(BaseModel):
    messaging_product: str | None = None
    contacts: list[dict[str, Any]] = Field(default_factory=list)
    messages: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def message_id(self) -> str | None:
        if not self.messages:
            return None
        value = self.messages[0].get("id")
        return str(value) if value else None


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
    result: list[WhatsAppInboundMessage] = []
    for entry in payload.entry:
        for change in entry.changes:
            if change.field != "messages" or change.value.metadata is None:
                continue
            contacts = {contact.wa_id: contact for contact in change.value.contacts}
            for message in change.value.messages:
                contact = contacts.get(message.from_number)
                result.append(
                    WhatsAppInboundMessage(
                        message_id=message.id,
                        phone_number_id=change.value.metadata.phone_number_id,
                        from_number=message.from_number,
                        display_name=contact.profile.name
                        if contact and contact.profile
                        else None,
                        message_type=message.type,
                        text=_message_text(message),
                        occurred_at=_timestamp(message.timestamp),
                        provider_content=_provider_content(message),
                    )
                )
    return result


def _timestamp(value: str) -> datetime:
    try:
        return datetime.fromtimestamp(int(value), tz=UTC)
    except (ValueError, OverflowError):
        return datetime.now(UTC)


def _message_text(message: WhatsAppMessage) -> str:
    if message.type == "text" and message.text:
        return message.text.body
    content = _provider_content(message)
    caption = content.get("caption")
    if caption:
        return f"[WhatsApp {message.type}] {caption}"
    if message.type == "location":
        latitude = content.get("latitude")
        longitude = content.get("longitude")
        return f"[WhatsApp location] {latitude}, {longitude}"
    if message.type == "button":
        return str(content.get("text") or "[WhatsApp button response]")
    if message.type == "interactive":
        reply = content.get("button_reply") or content.get("list_reply") or {}
        return str(reply.get("title") or reply.get("id") or "[WhatsApp interactive response]")
    return f"[WhatsApp {message.type} message]"


def _provider_content(message: WhatsAppMessage) -> dict[str, Any]:
    value = getattr(message, message.type, None)
    return dict(value) if isinstance(value, dict) else {}
