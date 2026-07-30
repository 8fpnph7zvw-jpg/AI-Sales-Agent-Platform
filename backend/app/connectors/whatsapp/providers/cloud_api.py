from __future__ import annotations

import hashlib
import hmac
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

CLOUD_API_REQUIRED_CONFIG_KEYS = (
    "phone_number_id",
    "access_token",
    "verify_token",
    "app_secret",
)
CLOUD_API_SECRET_CONFIG_KEYS = frozenset({"access_token", "verify_token", "app_secret"})


@whatsapp_provider_registry.register("cloud_api")
class WhatsAppCloudAPIAdapter(WhatsAppProviderAdapter):
    adapter_key = "cloud_api"

    @classmethod
    def validate_config(cls, config: dict[str, Any]) -> list[str]:
        return [
            f"{key} is required"
            for key in CLOUD_API_REQUIRED_CONFIG_KEYS
            if not str(config.get(key) or "").strip()
        ]

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        errors = self.validate_config(config)
        if errors:
            raise ServiceConfigurationError("; ".join(errors))
        base_url = str(config["graph_api_base_url"]).rstrip("/")
        version = str(config["graph_api_version"]).strip("/")
        self.phone_number_id = str(config["phone_number_id"]).strip()
        self.access_token = str(config["access_token"])
        self.verify_token = str(config["verify_token"])
        self.app_secret = str(config["app_secret"])
        self.timeout = float(config.get("timeout_seconds") or 15)
        self.base_url = f"{base_url}/{version}"

    async def health_check(self) -> HealthResult:
        started = perf_counter()
        data = await self._request(
            "GET",
            self.phone_number_id,
            params={"fields": "display_phone_number,verified_name"},
        )
        latency_ms = int((perf_counter() - started) * 1000)
        display_name = data.get("verified_name") or data.get("display_phone_number")
        return HealthResult(
            status="healthy",
            message=f"WhatsApp Cloud API connected{f' as {display_name}' if display_name else ''}.",
            latency_ms=latency_ms,
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
        self._verify_signature(raw_body, headers.get("x-hub-signature-256"))
        if payload.get("object") != "whatsapp_business_account":
            return []

        envelopes: list[UnifiedMessageEnvelope] = []
        for entry in payload.get("entry") or []:
            for change in entry.get("changes") or []:
                if change.get("field") != "messages":
                    continue
                value = change.get("value") or {}
                metadata = value.get("metadata") or {}
                contacts = {
                    str(contact.get("wa_id")): (contact.get("profile") or {}).get("name")
                    for contact in value.get("contacts") or []
                    if contact.get("wa_id")
                }
                for message in value.get("messages") or []:
                    message_id = str(message.get("id") or "")
                    sender = str(message.get("from") or "")
                    if not message_id or not sender:
                        continue
                    message_type = str(message.get("type") or "unknown")
                    text = self._message_text(message, message_type)
                    occurred_at = self._timestamp(message.get("timestamp"))
                    envelopes.append(
                        UnifiedMessageEnvelope(
                            external_message_id=message_id,
                            idempotency_key=f"whatsapp:{self.adapter_key}:{message_id}",
                            tenant_id=tenant_id,
                            channel="whatsapp",
                            direction=Direction.INBOUND,
                            message_type=MessageType.TEXT,
                            conversation_id=sender,
                            sender=Party(
                                id=sender,
                                display_name=contacts.get(sender),
                                address=f"whatsapp:{sender}",
                            ),
                            recipients=[
                                Party(
                                    id=str(
                                        metadata.get("phone_number_id")
                                        or metadata.get("display_phone_number")
                                        or self.phone_number_id
                                    ),
                                    address=f"whatsapp:{self.phone_number_id}",
                                )
                            ],
                            content=TextContent(text=text),
                            context=MessageContext(
                                attributes={
                                    "provider": self.adapter_key,
                                    "provider_message_type": message_type,
                                    "provider_content": message,
                                }
                            ),
                            occurred_at=occurred_at,
                        )
                    )
        return envelopes

    async def send(self, message: UnifiedMessageEnvelope) -> SendResult:
        if not isinstance(message.content, TextContent):
            raise ServiceConfigurationError(
                "WhatsApp Cloud API adapter currently sends normalized text messages only."
            )
        recipient = "".join(
            character
            for character in message.recipients[0].id
            if character.isdigit()
        )
        data = await self._request(
            "POST",
            f"{self.phone_number_id}/messages",
            json={
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": recipient,
                "type": "text",
                "text": {"body": message.content.text},
            },
        )
        messages = data.get("messages") or []
        provider_request_id = str(messages[0].get("id")) if messages else None
        return SendResult(
            accepted=bool(provider_request_id),
            provider_request_id=provider_request_id,
            detail="accepted" if provider_request_id else "Provider returned no message ID.",
        )

    def verify_challenge(self, mode: str, token: str, challenge: str) -> str:
        if mode != "subscribe" or not hmac.compare_digest(token, self.verify_token):
            raise AppError(403, "WHATSAPP_VERIFY_TOKEN_INVALID", "Webhook verification failed.")
        return challenge

    def _verify_signature(self, raw_body: bytes, signature: str | None) -> None:
        if not signature or not signature.startswith("sha256="):
            raise AppError(403, "WHATSAPP_SIGNATURE_INVALID", "Webhook signature is missing.")
        expected = hmac.new(
            self.app_secret.encode(),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(signature[7:], expected):
            raise AppError(403, "WHATSAPP_SIGNATURE_INVALID", "Webhook signature is invalid.")

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(
                    method,
                    f"{self.base_url}/{path.lstrip('/')}",
                    headers={"Authorization": f"Bearer {self.access_token}"},
                    **kwargs,
                )
                response.raise_for_status()
                value = response.json()
                return value if isinstance(value, dict) else {}
        except httpx.TimeoutException as exc:
            raise UpstreamServiceError("WhatsApp Cloud API", "request timed out") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise UpstreamServiceError("WhatsApp Cloud API", "request failed") from exc

    @staticmethod
    def _timestamp(value: Any) -> datetime:
        try:
            return datetime.fromtimestamp(float(value), tz=UTC)
        except (TypeError, ValueError, OverflowError):
            return datetime.now(UTC)

    @staticmethod
    def _message_text(message: dict[str, Any], message_type: str) -> str:
        if message_type == "text":
            body = (message.get("text") or {}).get("body")
            if body:
                return str(body)
        return f"[WhatsApp {message_type} message]"
