from __future__ import annotations

from typing import Any

from app.connectors.base import (
    BaseConnector,
    ConnectorCapability,
    ConnectorContext,
    HealthResult,
    SendResult,
)
from app.connectors.registry import connector_registry
from app.connectors.whatsapp.provider import whatsapp_provider_registry
from app.connectors.whatsapp.providers.cloud_api import (
    CLOUD_API_REQUIRED_CONFIG_KEYS,
    CLOUD_API_SECRET_CONFIG_KEYS,
)
from app.core.config import Settings, get_settings
from app.core.exceptions import ServiceConfigurationError
from app.schemas.protocol import UnifiedMessageEnvelope

DEFAULT_ADAPTER = "cloud_api"
SUPPORTED_CONFIG_KEYS = frozenset(
    {"adapter", *CLOUD_API_REQUIRED_CONFIG_KEYS}
)
REQUIRED_CONFIG_KEYS = CLOUD_API_REQUIRED_CONFIG_KEYS
SECRET_CONFIG_KEYS = CLOUD_API_SECRET_CONFIG_KEYS


@connector_registry.register("whatsapp")
class WhatsAppConnector(BaseConnector):
    """Provider-neutral WhatsApp business connector."""

    provider = "whatsapp"
    display_name = "WhatsApp Business"
    capabilities = frozenset(
        {
            ConnectorCapability.RECEIVE_MESSAGES,
            ConnectorCapability.SEND_MESSAGES,
            ConnectorCapability.TEXT,
            ConnectorCapability.MEDIA,
            ConnectorCapability.DELIVERY_RECEIPTS,
            ConnectorCapability.WEBHOOKS,
        }
    )

    def __init__(
        self,
        context: ConnectorContext,
        settings: Settings | None = None,
    ) -> None:
        super().__init__(context)
        self.settings = settings or get_settings()
        adapter_key = str(context.config.get("adapter") or DEFAULT_ADAPTER).strip().lower()
        adapter_type = whatsapp_provider_registry.get(adapter_key)
        if adapter_type is None:
            supported = ", ".join(whatsapp_provider_registry.keys()) or "none"
            raise ServiceConfigurationError(
                f"Unsupported WhatsApp provider adapter '{adapter_key}'. Supported: {supported}."
            )
        provider_config = {
            **context.config,
            "graph_api_base_url": self.settings.whatsapp_graph_api_base_url,
            "graph_api_version": self.settings.whatsapp_graph_api_version,
            "timeout_seconds": self.settings.whatsapp_timeout_seconds,
        }
        self.adapter_key = adapter_key
        self.adapter = adapter_type(provider_config)

    @classmethod
    def validate_config(cls, config: dict[str, Any]) -> list[str]:
        adapter_key = str(config.get("adapter") or DEFAULT_ADAPTER).strip().lower()
        adapter_type = whatsapp_provider_registry.get(adapter_key)
        if adapter_type is None:
            return [f"adapter must be one of: {', '.join(whatsapp_provider_registry.keys())}"]
        return adapter_type.validate_config(config)

    async def connect(self) -> None:
        errors = self.validate_config(self.context.config)
        if errors:
            raise ServiceConfigurationError("; ".join(errors))

    async def disconnect(self) -> None:
        return None

    async def health_check(self) -> HealthResult:
        await self.connect()
        return await self.adapter.health_check()

    async def normalize_inbound(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
        raw_body: bytes = b"",
    ) -> list[UnifiedMessageEnvelope]:
        await self.connect()
        return await self.adapter.normalize_inbound(
            payload,
            headers,
            raw_body,
            tenant_id=self.context.tenant_id,
            connector_id=self.context.connector_id,
        )

    async def send(self, message: UnifiedMessageEnvelope) -> SendResult:
        await self.connect()
        return await self.adapter.send(message)

    def verify_challenge(self, mode: str, token: str, challenge: str) -> str:
        return self.adapter.verify_challenge(mode, token, challenge)
