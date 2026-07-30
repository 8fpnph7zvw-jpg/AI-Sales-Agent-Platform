from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from app.schemas.protocol import UnifiedMessageEnvelope


class ConnectorCapability(StrEnum):
    RECEIVE_MESSAGES = "receive_messages"
    SEND_MESSAGES = "send_messages"
    TEXT = "text"
    MEDIA = "media"
    ORDERS = "orders"
    EVENTS = "events"
    DELIVERY_RECEIPTS = "delivery_receipts"
    WEBHOOKS = "webhooks"


@dataclass(frozen=True, slots=True)
class ConnectorContext:
    tenant_id: str
    connector_id: str
    config: dict[str, Any]
    credentials_ref: str | None = None


@dataclass(frozen=True, slots=True)
class HealthResult:
    status: str
    message: str
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    latency_ms: int | None = None


@dataclass(frozen=True, slots=True)
class SendResult:
    accepted: bool
    provider_request_id: str | None = None
    detail: str | None = None


class BaseConnector(ABC):
    """Platform adapter contract.

    Implementations own platform authentication and mapping. Core services must
    only exchange UnifiedMessageEnvelope values with connectors.
    """

    provider: str
    display_name: str
    capabilities: frozenset[ConnectorCapability] = frozenset()

    def __init__(self, context: ConnectorContext) -> None:
        self.context = context

    @classmethod
    @abstractmethod
    def validate_config(cls, config: dict[str, Any]) -> list[str]:
        """Return validation errors without contacting the remote platform."""

    @abstractmethod
    async def connect(self) -> None:
        """Initialize local resources; must be safe to call repeatedly."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Release resources without deleting persisted configuration."""

    @abstractmethod
    async def health_check(self) -> HealthResult:
        """Check readiness. Implementations should use short network timeouts."""

    @abstractmethod
    async def normalize_inbound(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
        raw_body: bytes = b"",
    ) -> list[UnifiedMessageEnvelope]:
        """Verify and convert a platform webhook into protocol envelopes."""

    @abstractmethod
    async def send(self, message: UnifiedMessageEnvelope) -> SendResult:
        """Send a normalized outbound message."""
