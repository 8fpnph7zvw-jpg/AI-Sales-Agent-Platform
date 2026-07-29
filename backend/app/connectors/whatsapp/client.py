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
STARTABLE_OPENWA_STATUSES = {"created", "disconnected", "failed"}
OPENWA_STATUS_MAP = {
    "created": "created",
    "starting": "starting",
    "reconnecting": "starting",
    "initializing": "starting",
    "authenticating": "starting",
    "authenticated": "connected",
    "qr": "waiting_qr",
    "qr_ready": "waiting_qr",
    "waiting_qr": "waiting_qr",
    "ready": "connected",
    "connected": "connected",
    "disconnected": "disconnected",
    "degraded": "disconnected",
    "auth_failure": "disconnected",
    "failed": "error",
    "error": "error",
}


class OpenWAClient:
    def __init__(
        self,
        settings: Settings,
        *,
        session_id: str | None = None,
        session_name: str | None = None,
    ) -> None:
        self.base_url = settings.openwa_url.rstrip("/") + "/"
        self.api_key = settings.openwa_api_key
        self.session_id = (
            str(session_id).strip()
            if session_id and UUID_PATTERN.fullmatch(str(session_id).strip())
            else None
        )
        self.session_name = self._resolve_session_name(
            session_name or (session_id if self.session_id is None else None),
            settings.openwa_session_name,
        )
        self.timeout = settings.whatsapp_timeout_seconds

    async def test_connection(self) -> dict[str, Any]:
        value = await self._find_session()
        return value or {
            "name": self.session_name,
            "status": "disconnected",
        }

    async def session_status(self) -> OpenWASessionStatusResponse:
        if not self.api_key:
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
            self.session_name = self._resolve_session_name(name, self.session_name)
        return await self.ensure_session_started()

    async def ensure_session_started(self) -> OpenWASessionStatusResponse:
        value = await self._find_session()
        if value is None:
            response = await self._request(
                "POST",
                "sessions",
                allowed_statuses={409},
                json={"name": self.session_name},
            )
            logger.info(
                "OpenWA API: create session name=%s status=%s",
                self.session_name,
                response.status_code,
            )
            if response.status_code == 409:
                value = await self._find_session()
                if value is None:
                    raise UpstreamServiceError(
                        "OpenWA",
                        f"session {self.session_name} already exists but cannot be read",
                    )
            else:
                value = dict(response.json())
        self._capture_identity(value)

        upstream_status = str(value.get("status") or "created").lower()
        if upstream_status in STARTABLE_OPENWA_STATUSES:
            response = await self._request(
                "POST",
                f"sessions/{self._required_session_id()}/start",
                allowed_statuses={400, 409},
            )
            logger.info(
                "OpenWA API: start session id=%s status=%s",
                self.session_id,
                response.status_code,
            )
            if response.status_code not in {400, 409}:
                value = dict(response.json())
            else:
                current = await self._refresh_session()
                if current is not None:
                    value = current
            self._capture_identity(value)
        return self._session_response(value)

    async def qrcode(self) -> OpenWAQRCodeResponse:
        session = await self.ensure_session_started()
        if session.status == "connected":
            return OpenWAQRCodeResponse(
                session_id=self._required_session_id(),
                status="connected",
                message="WhatsApp is already connected; no QR code is required.",
            )

        attempts = max(2, min(12, int(self.timeout)))
        for attempt in range(attempts):
            current = await self._refresh_session()
            if current is None:
                break
            mapped_status = self.normalize_status(current.get("status"))
            if mapped_status == "connected":
                return OpenWAQRCodeResponse(
                    session_id=self._required_session_id(),
                    status="connected",
                    message="WhatsApp connected while waiting for the QR code.",
                )
            if mapped_status == "waiting_qr":
                response = await self._request(
                    "GET",
                    f"sessions/{self._required_session_id()}/qr",
                    allowed_statuses={400, 404, 409},
                )
                logger.info(
                    "OpenWA API: get qr session_id=%s status=%s",
                    self.session_id,
                    response.status_code,
                )
                if response.status_code < 400:
                    value = dict(response.json())
                    data_url = value.get("dataUrl") or value.get("qrCode")
                    if not data_url:
                        data_url = value.get("qr")
                    if data_url:
                        return OpenWAQRCodeResponse(
                            session_id=self._required_session_id(),
                            status="waiting_qr",
                            data_url=str(data_url),
                            message="Scan the QR code with WhatsApp.",
                        )
            if attempt < attempts - 1:
                await asyncio.sleep(0.5)

        latest = await self.session_status()
        return OpenWAQRCodeResponse(
            session_id=latest.session_id or self.session_name,
            status=latest.status,
            message=(
                "OpenWA is still starting. The QR code is not ready yet; please retry shortly."
                if latest.status in {"created", "starting"}
                else "No QR code is currently available."
            ),
        )

    async def delete_session(self) -> OpenWASessionStatusResponse:
        value = await self._find_session()
        if value is not None:
            await self._request(
                "DELETE",
                f"sessions/{self._required_session_id()}",
                allowed_statuses={404},
            )
        self.session_id = None
        return OpenWASessionStatusResponse(
            name=self.session_name,
            status="disconnected",
            api_key_configured=bool(self.api_key),
        )

    async def reconnect(self) -> OpenWASessionStatusResponse:
        value = await self._find_session()
        if value is None:
            raise UpstreamServiceError(
                "OpenWA",
                "the bound session was not found; refusing to create a replacement session",
            )
        response = await self._request(
            "POST",
            f"sessions/{self._required_session_id()}/reconnect",
            allowed_statuses={202, 404, 409},
        )
        if response.status_code == 404:
            logger.info(
                "OpenWA API has no reconnect route; restarting existing session id=%s",
                self.session_id,
            )
            response = await self._request(
                "POST",
                f"sessions/{self._required_session_id()}/start",
                allowed_statuses={202, 400, 404, 409},
            )
            if response.status_code == 404:
                raise UpstreamServiceError(
                    "OpenWA",
                    "does not support reconnect or start for the existing session",
                )
        if response.status_code == 409:
            current = await self._refresh_session()
            return self._session_response(current or value)
        if response.status_code == 400:
            current = await self._refresh_session()
            return self._session_response(current or value)
        restarted = dict(response.json())
        self._capture_identity(restarted)
        return self._session_response(restarted)

    async def send_text(self, recipient: str, text: str) -> WhatsAppSendResponse:
        value = await self._find_session()
        if value is None:
            raise UpstreamServiceError(
                "OpenWA",
                f"session {self.session_name} does not exist",
            )
        chat_id = normalize_chat_id(recipient)
        logger.info(
            "send_message_request session_id=%s phone=%s message=%r status=pending",
            self.session_id,
            recipient,
            text[:500],
        )
        try:
            response = await self._request(
                "POST",
                f"sessions/{self._required_session_id()}/messages/send-text",
                json={"chatId": chat_id, "text": text},
            )
            result = WhatsAppSendResponse.model_validate(response.json())
        except Exception as exc:
            logger.exception(
                "send_message_response session_id=%s phone=%s message=%r "
                "status=failed error=%s",
                self.session_id,
                recipient,
                text[:500],
                str(exc)[:1000],
            )
            raise
        logger.info(
            "send_message_response session_id=%s phone=%s message=%r "
            "status=sent provider_message_id=%s error=null",
            self.session_id,
            recipient,
            text[:500],
            result.message_id,
        )
        return result

    async def _list_sessions(self) -> list[dict[str, Any]]:
        response = await self._request("GET", "sessions")
        payload = response.json()
        if isinstance(payload, list):
            return [dict(item) for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict) and isinstance(payload.get("data"), list):
            return [
                dict(item)
                for item in payload["data"]
                if isinstance(item, dict)
            ]
        return []

    async def _find_session(self) -> dict[str, Any] | None:
        sessions = await self._list_sessions()
        value = next(
            (
                item
                for item in sessions
                if (
                    self.session_id
                    and str(item.get("id") or "") == self.session_id
                )
                or str(item.get("name") or "") == self.session_name
            ),
            None,
        )
        if value is not None:
            self._capture_identity(value)
        return value

    async def _refresh_session(self) -> dict[str, Any] | None:
        if not self.session_id:
            return await self._find_session()
        response = await self._request(
            "GET",
            f"sessions/{self.session_id}",
            allowed_statuses={404},
        )
        if response.status_code == 404:
            return await self._find_session()
        value = dict(response.json())
        self._capture_identity(value)
        return value

    def _capture_identity(self, value: dict[str, Any]) -> None:
        identifier = str(value.get("id") or "").strip()
        if UUID_PATTERN.fullmatch(identifier):
            self.session_id = identifier
        name = str(value.get("name") or "").strip()
        if SESSION_NAME_PATTERN.fullmatch(name):
            self.session_name = name

    def _required_session_id(self) -> str:
        if not self.session_id:
            raise UpstreamServiceError(
                "OpenWA",
                f"session {self.session_name} has no valid ID",
            )
        return self.session_id

    @classmethod
    def normalize_status(cls, value: Any) -> str:
        return OPENWA_STATUS_MAP.get(str(value or "").lower(), "error")

    def _session_response(self, value: dict[str, Any]) -> OpenWASessionStatusResponse:
        self._capture_identity(value)
        upstream_status = str(value.get("status") or "disconnected").lower()
        status = self.normalize_status(upstream_status)
        return OpenWASessionStatusResponse(
            session_id=self.session_id,
            name=str(value.get("name") or self.session_name),
            status=status,
            api_key_configured=bool(self.api_key),
            qr_available=(
                status != "connected"
                and (
                    bool(value.get("qrAvailable"))
                    or status == "waiting_qr"
                )
            ),
            phone_number=value.get("phoneNumber") or value.get("phone"),
            last_error=value.get("lastError") or value.get("last_error"),
            session_data=(
                dict(value["sessionData"])
                if isinstance(value.get("sessionData"), dict)
                else None
            ),
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
        headers = {
            "x-api-key": self.api_key,
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
                try:
                    error_payload = exc.response.json()
                    upstream_detail = (
                        error_payload.get("error")
                        if isinstance(error_payload, dict)
                        else None
                    )
                except ValueError:
                    upstream_detail = None
                logger.warning(
                    "openwa_http_error status=%s path=%s",
                    exc.response.status_code,
                    path,
                )
                raise UpstreamServiceError(
                    "OpenWA",
                    (
                        f"returned HTTP {exc.response.status_code}: "
                        f"{str(upstream_detail)[:500]}"
                        if upstream_detail
                        else f"returned HTTP {exc.response.status_code}"
                    ),
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
            session_id=(
                str(context.config["openwa_session_id"])
                if context.config.get("openwa_session_id")
                else None
            ),
            session_name=str(
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
        status = self.client.normalize_status(data.get("status"))
        return HealthResult(
            status="healthy" if status == "connected" else "degraded",
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
