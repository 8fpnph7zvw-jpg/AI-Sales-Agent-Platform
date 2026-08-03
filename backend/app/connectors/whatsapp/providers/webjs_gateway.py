from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

import httpx

from app.connectors.base import HealthResult, SendResult
from app.connectors.whatsapp.provider import (
    WhatsAppProviderAdapter,
    whatsapp_provider_registry,
)
from app.core.exceptions import AppError, ServiceConfigurationError, UpstreamServiceError
from app.schemas.protocol import (
    Direction,
    MessageContext,
    MessageType,
    Party,
    TextContent,
    UnifiedMessageEnvelope,
)

WEBJS_GATEWAY_REQUIRED_CONFIG_KEYS = ("session_id",)
WEBJS_GATEWAY_SECRET_CONFIG_KEYS = frozenset()

logger = logging.getLogger(__name__)


@whatsapp_provider_registry.register("webjs_gateway")
class WhatsAppWebJsGatewayAdapter(WhatsAppProviderAdapter):
    adapter_key = "webjs_gateway"

    @classmethod
    def validate_config(cls, config: dict[str, Any]) -> list[str]:
        return [
            f"{key} is required"
            for key in WEBJS_GATEWAY_REQUIRED_CONFIG_KEYS
            if not str(config.get(key) or "").strip()
        ]

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        errors = self.validate_config(config)
        errors.extend(
            f"{key} is required"
            for key in ("gateway_url", "gateway_token")
            if not str(config.get(key) or "").strip()
        )
        if errors:
            raise ServiceConfigurationError("; ".join(errors))
        self.gateway_url = str(config["gateway_url"]).rstrip("/")
        self.gateway_token = str(config["gateway_token"])
        self.session_id = str(config["session_id"])
        self.timeout = float(config.get("timeout_seconds") or 15)

    async def health_check(self) -> HealthResult:
        started = perf_counter()
        data = await self._request(
            "GET",
            "/api/whatsapp/status",
            params={"sessionId": self.session_id},
        )
        status = str(data.get("status") or "DISCONNECTED")
        return HealthResult(
            status="healthy" if status == "CONNECTED" else "unhealthy",
            message=f"whatsapp-web.js gateway session is {status}.",
            latency_ms=int((perf_counter() - started) * 1000),
        )

    async def connect_session(self) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/api/whatsapp/connect",
            json={"sessionId": self.session_id},
        )

    async def session_status(self) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/api/whatsapp/status",
            params={"sessionId": self.session_id},
        )

    async def session_qr(self) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/api/whatsapp/qr",
            params={"sessionId": self.session_id},
        )

    async def reconnect_session(self) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/api/whatsapp/reconnect",
            json={"sessionId": self.session_id},
        )

    async def disconnect_session(self) -> dict[str, Any]:
        return await self._request(
            "DELETE",
            "/api/whatsapp/session",
            json={"sessionId": self.session_id},
        )

    async def normalize_inbound(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
        raw_body: bytes,
        *,
        tenant_id: str,
        connector_id: str,
    ) -> list[UnifiedMessageEnvelope]:
        supplied_token = headers.get("x-whatsapp-gateway-token", "")
        if not hmac.compare_digest(supplied_token, self.gateway_token):
            raise AppError(
                403,
                "WHATSAPP_GATEWAY_TOKEN_INVALID",
                "WhatsApp gateway authentication failed.",
            )
        phone = "".join(
            character
            for character in str(payload.get("phone") or "")
            if character.isdigit()
        )
        text = str(payload.get("message") or "").strip()
        message_id = str(
            payload.get("message_id")
            or headers.get("x-request-id")
            or hashlib.sha256(raw_body).hexdigest()
        ).strip()
        if not phone or not text:
            raise AppError(
                422,
                "WHATSAPP_GATEWAY_PAYLOAD_INVALID",
                "phone and message are required.",
            )
        timestamp = payload.get("timestamp")
        try:
            occurred_at = (
                datetime.fromtimestamp(float(timestamp), tz=UTC)
                if timestamp is not None
                else datetime.now(UTC)
            )
        except (OverflowError, TypeError, ValueError) as exc:
            raise AppError(
                422,
                "WHATSAPP_GATEWAY_TIMESTAMP_INVALID",
                "timestamp must be a valid Unix timestamp.",
            ) from exc
        return [
            UnifiedMessageEnvelope(
                external_message_id=message_id,
                idempotency_key=f"whatsapp:{self.adapter_key}:{message_id}",
                tenant_id=tenant_id,
                channel="whatsapp",
                direction=Direction.INBOUND,
                message_type=MessageType.TEXT,
                conversation_id=phone,
                sender=Party(id=phone, address=f"whatsapp:{phone}"),
                recipients=[
                    Party(
                        id=connector_id,
                        address=f"whatsapp-session:{self.session_id}",
                    )
                ],
                content=TextContent(text=text),
                context=MessageContext(
                    attributes={
                        "provider": self.adapter_key,
                        "provider_message_type": "text",
                        "provider_content": {
                            "session_id": self.session_id,
                            "channel": payload.get("channel"),
                        },
                    }
                ),
                occurred_at=occurred_at,
            )
        ]

    async def send(self, message: UnifiedMessageEnvelope) -> SendResult:
        if not isinstance(message.content, TextContent):
            raise ServiceConfigurationError(
                "whatsapp-web.js gateway currently sends normalized text messages only."
            )
        data = await self._request(
            "POST",
            "/api/whatsapp/send",
            json={
                "phone": message.recipients[0].id,
                "message": message.content.text,
                "sessionId": self.session_id,
            },
        )
        message_id = str(data.get("messageId") or "") or None
        status = str(data.get("status") or "").strip().upper()
        accepted = bool(message_id) or data.get("sent") is True or status == "SENT"
        if accepted and message_id is None:
            logger.warning(
                "Gateway sent message but no message ID returned. "
                "session_id=%s status=%s",
                self.session_id,
                status or "none",
            )
        return SendResult(
            accepted=accepted,
            provider_request_id=message_id,
            detail="accepted" if accepted else "Gateway did not confirm the message was sent.",
        )

    def verify_challenge(self, mode: str, token: str, challenge: str) -> str:
        del mode, token, challenge
        raise AppError(
            405,
            "WHATSAPP_GATEWAY_CHALLENGE_UNSUPPORTED",
            "The whatsapp-web.js gateway does not use webhook challenges.",
        )

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        headers = kwargs.pop("headers", {})
        headers["X-WhatsApp-Gateway-Token"] = self.gateway_token
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(
                    method,
                    f"{self.gateway_url}/{path.lstrip('/')}",
                    headers=headers,
                    **kwargs,
                )
                response.raise_for_status()
                value = response.json()
                return value if isinstance(value, dict) else {}
        except httpx.HTTPStatusError as exc:
            raise UpstreamServiceError(
                "whatsapp-web.js gateway",
                f"HTTP {exc.response.status_code}",
                retryable=exc.response.status_code >= 500,
                upstream_status_code=exc.response.status_code,
                error_code="WHATSAPP_GATEWAY_HTTP_ERROR",
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise UpstreamServiceError(
                "whatsapp-web.js gateway",
                str(exc),
                retryable=True,
                error_code="WHATSAPP_GATEWAY_UNAVAILABLE",
            ) from exc
