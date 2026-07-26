from __future__ import annotations

import asyncio
import logging
from time import perf_counter
from typing import Any

import httpx

from app.connectors.base import (
    BaseConnector,
    ConnectorCapability,
    ConnectorContext,
    HealthResult,
    SendResult,
)
from app.connectors.registry import connector_registry
from app.connectors.whatsapp.schemas import (
    WhatsAppSendResponse,
    WhatsAppWebhookPayload,
    parse_inbound_messages,
)
from app.core.config import Settings
from app.core.exceptions import ServiceConfigurationError, UpstreamServiceError
from app.schemas.protocol import (
    Direction,
    MessageContext,
    MessageType,
    Party,
    TextContent,
    UnifiedMessageEnvelope,
)

logger = logging.getLogger(__name__)

REQUIRED_CONFIG_KEYS = (
    "phone_number_id",
    "business_account_id",
    "access_token",
    "verify_token",
)
SECRET_CONFIG_KEYS = frozenset({"access_token", "verify_token", "app_secret"})


class WhatsAppApiClient:
    def __init__(
        self,
        settings: Settings,
        *,
        phone_number_id: str,
        access_token: str,
    ) -> None:
        self.base_url = (
            f"{settings.whatsapp_graph_api_base_url.rstrip('/')}/"
            f"{settings.whatsapp_graph_api_version}"
        )
        self.phone_number_id = phone_number_id
        self.access_token = access_token
        self.timeout = settings.whatsapp_timeout_seconds

    async def test_connection(self) -> dict[str, Any]:
        response = await self._request(
            "GET",
            self.phone_number_id,
            params={"fields": "id,display_phone_number,verified_name,quality_rating"},
        )
        return dict(response.json())

    async def send_text(self, recipient: str, text: str) -> WhatsAppSendResponse:
        response = await self._request(
            "POST",
            f"{self.phone_number_id}/messages",
            json={
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": recipient,
                "type": "text",
                "text": {"preview_url": False, "body": text},
            },
        )
        return WhatsAppSendResponse.model_validate(response.json())

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(
                    base_url=self.base_url,
                    timeout=self.timeout,
                ) as client:
                    response = await client.request(
                        method,
                        path,
                        headers=headers,
                        **kwargs,
                    )
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < 2:
                        await asyncio.sleep(0.25 * (2**attempt))
                        continue
                response.raise_for_status()
                return response
            except httpx.TimeoutException as exc:
                if attempt < 2:
                    await asyncio.sleep(0.25 * (2**attempt))
                    continue
                raise UpstreamServiceError("WhatsApp", "request timed out") from exc
            except httpx.HTTPStatusError as exc:
                logger.warning(
                    "whatsapp_api_http_error status=%s path=%s",
                    exc.response.status_code,
                    path,
                )
                raise UpstreamServiceError(
                    "WhatsApp",
                    f"returned HTTP {exc.response.status_code}",
                ) from exc
            except httpx.HTTPError as exc:
                raise UpstreamServiceError("WhatsApp", "request failed") from exc
        raise UpstreamServiceError("WhatsApp", "request failed after retries")


@connector_registry.register("whatsapp")
class WhatsAppConnector(BaseConnector):
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

    def __init__(self, context: ConnectorContext, settings: Settings) -> None:
        super().__init__(context)
        self.settings = settings
        self.client = WhatsAppApiClient(
            settings,
            phone_number_id=str(context.config.get("phone_number_id") or ""),
            access_token=str(context.config.get("access_token") or ""),
        )

    @classmethod
    def validate_config(cls, config: dict[str, Any]) -> list[str]:
        return [
            f"{key} is required"
            for key in REQUIRED_CONFIG_KEYS
            if not str(config.get(key) or "").strip()
        ]

    async def connect(self) -> None:
        errors = self.validate_config(self.context.config)
        if errors:
            raise ServiceConfigurationError("; ".join(errors))

    async def disconnect(self) -> None:
        return None

    async def health_check(self) -> HealthResult:
        await self.connect()
        started = perf_counter()
        data = await self.client.test_connection()
        latency_ms = int((perf_counter() - started) * 1000)
        verified_name = str(data.get("verified_name") or "WhatsApp Business")
        return HealthResult(
            status="healthy",
            message=f"Connected to {verified_name}",
            latency_ms=latency_ms,
        )

    async def normalize_inbound(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> list[UnifiedMessageEnvelope]:
        parsed = WhatsAppWebhookPayload.model_validate(payload)
        messages = parse_inbound_messages(parsed)
        return [
            UnifiedMessageEnvelope(
                external_message_id=item.message_id,
                idempotency_key=f"whatsapp:{item.message_id}",
                tenant_id=self.context.tenant_id,
                channel=self.provider,
                direction=Direction.INBOUND,
                message_type=MessageType.TEXT,
                conversation_id=item.from_number,
                sender=Party(
                    id=item.from_number,
                    display_name=item.display_name,
                    address=f"whatsapp:{item.from_number}",
                ),
                recipients=[
                    Party(
                        id=item.phone_number_id,
                        address=f"whatsapp:{item.phone_number_id}",
                    )
                ],
                content=TextContent(text=item.text),
                context=MessageContext(
                    attributes={
                        "provider_message_type": item.message_type,
                        "provider_content": item.provider_content,
                        "request_id": headers.get("x-request-id"),
                    }
                ),
                occurred_at=item.occurred_at,
            )
            for item in messages
        ]

    async def send(self, message: UnifiedMessageEnvelope) -> SendResult:
        await self.connect()
        if not isinstance(message.content, TextContent):
            raise ServiceConfigurationError(
                "WhatsApp connector currently sends normalized text replies only."
            )
        response = await self.client.send_text(
            message.recipients[0].id,
            message.content.text,
        )
        return SendResult(
            accepted=response.message_id is not None,
            provider_request_id=response.message_id,
            detail="accepted" if response.message_id else "missing provider message id",
        )
