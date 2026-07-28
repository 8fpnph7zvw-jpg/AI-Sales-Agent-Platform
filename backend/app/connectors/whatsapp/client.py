from __future__ import annotations

import asyncio
import logging
import re
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
    OpenWAQRCodeResponse,
    OpenWASessionStatusResponse,
    WhatsAppSendResponse,
    WhatsAppWebhookPayload,
    normalize_chat_id,
    parse_inbound_messages,
)
from app.core.config import Settings, get_settings
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

REQUIRED_CONFIG_KEYS = ("session_id",)
SECRET_CONFIG_KEYS: frozenset[str] = frozenset()
DEFAULT_SESSION_NAME = "ai-sales-agent"
SESSION_NAME_PATTERN = re.compile(r"^[A-Za-z0-9-]{3,50}$")
UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


class OpenWAClient:
    def __init__(
        self,
        settings: Settings,
        *,
        session_id: str | None = None,
    ) -> None:
        self.base_url = settings.openwa_url.rstrip("/") + "/"
        self.api_key = settings.openwa_api_key
        self.session_id = self._resolve_session_name(
            session_id,
            settings.openwa_session_name,
        )
        self.timeout = settings.whatsapp_timeout_seconds

    async def test_connection(self) -> dict[str, Any]:
        response = await self._request("GET", f"sessions/{self.session_id}")
        return dict(response.json())

    async def session_status(self) -> OpenWASessionStatusResponse:
        if not self.api_key or not self.session_id:
            return OpenWASessionStatusResponse(
                status="disconnected",
                api_key_configured=bool(self.api_key),
            )
        value = await self._find_session()
        if value is None:
            return OpenWASessionStatusResponse(
                status="disconnected",
                api_key_configured=True,
            )
        return self._session_response(value)

    async def create_session(self, name: str | None = None) -> OpenWASessionStatusResponse:
        if name is not None:
            self.session_id = self._resolve_session_name(name, self.session_id)
        return await self.ensure_session_started()

    async def ensure_session_started(self) -> OpenWASessionStatusResponse:
        value = await self._find_session()
        if value is None:
            response = await self._request(
                "POST",
                "sessions",
                allowed_statuses={409},
                json={"name": self.session_id},
            )
            if response.status_code == 409:
                value = await self._find_session()
                if value is None:
                    raise UpstreamServiceError(
                        "OpenWA",
                        f"session {self.session_id} already exists but cannot be read",
                    )
            else:
                value = dict(response.json())

        response = await self._request(
            "POST",
            f"sessions/{self.session_id}/start",
            allowed_statuses={400, 409},
        )
        if response.status_code not in {400, 409}:
            value = dict(response.json())
        else:
            current = await self._find_session()
            if current is not None:
                value = current
        return self._session_response(value)

    async def qrcode(self) -> OpenWAQRCodeResponse:
        await self.ensure_session_started()
        attempts = max(1, min(30, int(self.timeout * 2)))
        for attempt in range(attempts):
            response = await self._request(
                "GET",
                f"sessions/{self.session_id}/qr",
                allowed_statuses={400, 404, 409},
            )
            if response.status_code < 400:
                value = dict(response.json())
                data_url = value.get("dataUrl") or value.get("qrCode")
                if data_url:
                    return OpenWAQRCodeResponse(
                        session_id=self.session_id,
                        status=str(value.get("status") or "qr"),
                        data_url=str(data_url),
                    )
            if attempt < attempts - 1:
                await asyncio.sleep(0.5)
        raise UpstreamServiceError(
            "OpenWA",
            f"QR code for session {self.session_id} is not ready",
        )

    async def delete_session(self) -> OpenWASessionStatusResponse:
        await self._request(
            "DELETE",
            f"sessions/{self.session_id}",
            allowed_statuses={404},
        )
        return OpenWASessionStatusResponse(
            status="disconnected",
            api_key_configured=bool(self.api_key),
        )

    async def reconnect(self) -> OpenWASessionStatusResponse:
        await self.delete_session()
        return await self.ensure_session_started()

    async def send_text(self, recipient: str, text: str) -> WhatsAppSendResponse:
        response = await self._request(
            "POST",
            f"sessions/{self.session_id}/messages/send-text",
            json={"chatId": normalize_chat_id(recipient), "text": text},
        )
        return WhatsAppSendResponse.model_validate(response.json())

    async def _find_session(self) -> dict[str, Any] | None:
        response = await self._request(
            "GET",
            f"sessions/{self.session_id}",
            allowed_statuses={404},
        )
        if response.status_code == 404:
            return None
        return dict(response.json())

    def _session_response(self, value: dict[str, Any]) -> OpenWASessionStatusResponse:
        status = str(value.get("status") or "disconnected")
        return OpenWASessionStatusResponse(
            session_id=self.session_id,
            name=str(value.get("name") or self.session_id),
            status=status,
            api_key_configured=bool(self.api_key),
            qr_available=bool(value.get("qrAvailable")) or status in {"qr", "qr_ready"},
            phone_number=value.get("phoneNumber") or value.get("phone"),
        )

    @staticmethod
    def _resolve_session_name(
        requested: str | None,
        configured_name: str | None,
    ) -> str:
        for candidate in (requested, configured_name, DEFAULT_SESSION_NAME):
            value = str(candidate or "").strip()
            if SESSION_NAME_PATTERN.fullmatch(value) and not UUID_PATTERN.fullmatch(value):
                return value
        return DEFAULT_SESSION_NAME

    async def _request(
        self,
        method: str,
        path: str,
        *,
        allowed_statuses: set[int] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        if not self.api_key:
            raise ServiceConfigurationError("OPENWA_API_KEY is required.")
        if not self.session_id:
            raise ServiceConfigurationError("OPENWA_SESSION_NAME is required.")
        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }
        max_attempts = 3 if method == "GET" else 1
        for attempt in range(max_attempts):
            try:
                async with httpx.AsyncClient(
                    base_url=self.base_url,
                    timeout=self.timeout,
                ) as client:
                    response = await client.request(method, path, headers=headers, **kwargs)
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < max_attempts - 1:
                        await asyncio.sleep(0.25 * (2**attempt))
                        continue
                if allowed_statuses and response.status_code in allowed_statuses:
                    return response
                response.raise_for_status()
                return response
            except httpx.TimeoutException as exc:
                if attempt < max_attempts - 1:
                    await asyncio.sleep(0.25 * (2**attempt))
                    continue
                raise UpstreamServiceError("OpenWA", "request timed out") from exc
            except httpx.HTTPStatusError as exc:
                logger.warning(
                    "openwa_http_error status=%s path=%s",
                    exc.response.status_code,
                    path,
                )
                raise UpstreamServiceError(
                    "OpenWA",
                    f"returned HTTP {exc.response.status_code}",
                ) from exc
            except httpx.HTTPError as exc:
                raise UpstreamServiceError("OpenWA", "request failed") from exc
        raise UpstreamServiceError("OpenWA", "request failed after retries")


@connector_registry.register("whatsapp")
class WhatsAppConnector(BaseConnector):
    provider = "whatsapp"
    display_name = "WhatsApp (OpenWA)"
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
        self.client = OpenWAClient(
            self.settings,
            session_id=str(
                context.config.get("session_id")
                or self.settings.openwa_session_name
            ),
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
        status = str(data.get("status") or "unknown")
        return HealthResult(
            status="healthy" if status == "ready" else "degraded",
            message=f"OpenWA session {self.client.session_id} is {status}",
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
                idempotency_key=parsed.idempotency_key,
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
                        id=item.to_number or item.session_id,
                        address=f"whatsapp:{item.to_number or item.session_id}",
                    )
                ],
                content=TextContent(text=item.text),
                context=MessageContext(
                    attributes={
                        "provider_message_type": item.message_type,
                        "provider_content": item.provider_content,
                        "request_id": headers.get("x-request-id"),
                        "openwa_delivery_id": parsed.delivery_id,
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
            accepted=bool(response.message_id),
            provider_request_id=response.message_id,
            detail="accepted",
        )
