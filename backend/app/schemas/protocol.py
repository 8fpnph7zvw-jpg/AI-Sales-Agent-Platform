from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Direction(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class MessageType(StrEnum):
    TEXT = "text"
    MEDIA = "media"
    ORDER = "order"
    EVENT = "event"


class Party(BaseModel):
    id: str = Field(min_length=1, max_length=255)
    display_name: str | None = Field(default=None, max_length=255)
    address: str | None = Field(default=None, max_length=500)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TextContent(BaseModel):
    type: Literal["text"] = "text"
    text: str = Field(min_length=1, max_length=20_000)


class MediaItem(BaseModel):
    media_id: str | None = None
    url: str | None = None
    mime_type: str
    filename: str | None = None
    caption: str | None = None

    @model_validator(mode="after")
    def media_has_locator(self) -> "MediaItem":
        if not self.media_id and not self.url:
            raise ValueError("media_id or url is required")
        return self


class MediaContent(BaseModel):
    type: Literal["media"] = "media"
    items: list[MediaItem] = Field(min_length=1, max_length=20)


class OrderLine(BaseModel):
    sku: str
    name: str
    quantity: int = Field(gt=0)
    unit_price: str
    currency: str = Field(min_length=3, max_length=3)


class OrderContent(BaseModel):
    type: Literal["order"] = "order"
    order_id: str
    state: str | None = None
    lines: list[OrderLine] = Field(default_factory=list)
    total: str | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)


class EventContent(BaseModel):
    type: Literal["event"] = "event"
    name: str = Field(min_length=1, max_length=120)
    data: dict[str, Any] = Field(default_factory=dict)


MessageContent = Annotated[
    TextContent | MediaContent | OrderContent | EventContent,
    Field(discriminator="type"),
]


class MessageContext(BaseModel):
    reply_to_message_id: str | None = None
    locale: str | None = None
    tags: list[str] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)


class TraceContext(BaseModel):
    trace_id: str = Field(default_factory=lambda: uuid4().hex)
    correlation_id: str | None = None
    causation_id: str | None = None


class UnifiedMessageEnvelope(BaseModel):
    """Versioned contract shared by all channel adapters and core services."""

    model_config = ConfigDict(extra="forbid")

    protocol_version: Literal["1.0"] = "1.0"
    message_id: UUID = Field(default_factory=uuid4)
    external_message_id: str | None = None
    idempotency_key: str = Field(min_length=8, max_length=255)
    tenant_id: str = Field(min_length=1, max_length=64)
    connector_id: UUID | None = None
    channel: str = Field(min_length=1, max_length=64)
    direction: Direction
    message_type: MessageType
    conversation_id: str = Field(min_length=1, max_length=255)
    sender: Party
    recipients: list[Party] = Field(min_length=1, max_length=100)
    content: MessageContent
    context: MessageContext = Field(default_factory=MessageContext)
    trace: TraceContext = Field(default_factory=TraceContext)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def content_matches_message_type(self) -> "UnifiedMessageEnvelope":
        if self.message_type.value != self.content.type:
            raise ValueError("message_type must match content.type")
        return self
