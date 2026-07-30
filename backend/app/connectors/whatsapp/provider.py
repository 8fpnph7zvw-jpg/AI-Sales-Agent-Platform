from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, TypeVar

from app.connectors.base import HealthResult, SendResult
from app.schemas.protocol import UnifiedMessageEnvelope


class WhatsAppProviderAdapter(ABC):
    """Provider boundary for WhatsApp transports.

    Core services depend on this contract instead of a provider runtime. A new
    transport only needs to implement this class and register its adapter key.
    """

    adapter_key: str

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    @classmethod
    @abstractmethod
    def validate_config(cls, config: dict[str, Any]) -> list[str]:
        """Return configuration errors without contacting the provider."""

    @abstractmethod
    async def health_check(self) -> HealthResult:
        """Check provider readiness."""

    @abstractmethod
    async def normalize_inbound(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
        raw_body: bytes,
        *,
        tenant_id: str,
        connector_id: str,
    ) -> list[UnifiedMessageEnvelope]:
        """Verify and normalize a provider webhook."""

    @abstractmethod
    async def send(self, message: UnifiedMessageEnvelope) -> SendResult:
        """Send a normalized outbound message."""

    @abstractmethod
    def verify_challenge(self, mode: str, token: str, challenge: str) -> str:
        """Validate a provider webhook subscription challenge."""


ProviderType = TypeVar("ProviderType", bound=type[WhatsAppProviderAdapter])


class WhatsAppProviderRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, type[WhatsAppProviderAdapter]] = {}

    def register(self, key: str) -> Callable[[ProviderType], ProviderType]:
        def decorator(adapter: ProviderType) -> ProviderType:
            normalized = key.strip().lower()
            if normalized in self._adapters:
                raise ValueError(f"WhatsApp provider adapter already registered: {normalized}")
            self._adapters[normalized] = adapter
            return adapter

        return decorator

    def get(self, key: str) -> type[WhatsAppProviderAdapter] | None:
        return self._adapters.get(key.strip().lower())

    def keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._adapters))


whatsapp_provider_registry = WhatsAppProviderRegistry()
