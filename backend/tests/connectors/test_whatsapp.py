from __future__ import annotations

import hashlib
import hmac
from typing import Any

import pytest

from app.connectors.base import ConnectorContext
from app.connectors.registry import connector_registry
from app.connectors.whatsapp.client import WhatsAppApiClient, WhatsAppConnector
from app.connectors.whatsapp.schemas import (
    WhatsAppWebhookPayload,
    parse_inbound_messages,
)
from app.connectors.whatsapp.service import WhatsAppService
from app.core.config import Settings
from app.core.exceptions import AppError
from app.schemas.protocol import Direction, TextContent

WEBHOOK_PAYLOAD = {
    "object": "whatsapp_business_account",
    "entry": [
        {
            "id": "waba-123",
            "changes": [
                {
                    "field": "messages",
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "display_phone_number": "15550001111",
                            "phone_number_id": "phone-123",
                        },
                        "contacts": [
                            {
                                "wa_id": "15551234567",
                                "profile": {"name": "Enterprise Buyer"},
                            }
                        ],
                        "messages": [
                            {
                                "from": "15551234567",
                                "id": "wamid.message-1",
                                "timestamp": "1710000000",
                                "type": "text",
                                "text": {"body": "Need 500 wireless earphones"},
                            }
                        ],
                    },
                }
            ],
        }
    ],
}


class FakeResponse:
    status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return {
            "messaging_product": "whatsapp",
            "contacts": [{"wa_id": "15551234567"}],
            "messages": [{"id": "wamid.outbound-1"}],
        }


class FakeAsyncClient:
    base_url: str | None = None
    method: str | None = None
    path: str | None = None
    headers: dict[str, str] | None = None
    request_json: dict[str, Any] | None = None

    def __init__(self, *, base_url: str, timeout: float) -> None:
        type(self).base_url = base_url

    async def __aenter__(self) -> FakeAsyncClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str],
        **kwargs: Any,
    ) -> FakeResponse:
        type(self).method = method
        type(self).path = path
        type(self).headers = headers
        type(self).request_json = kwargs.get("json")
        return FakeResponse()


def test_whatsapp_payload_is_normalized_without_losing_provider_identity() -> None:
    parsed = WhatsAppWebhookPayload.model_validate(WEBHOOK_PAYLOAD)

    messages = parse_inbound_messages(parsed)

    assert parsed.phone_number_ids() == {"phone-123"}
    assert len(messages) == 1
    assert messages[0].message_id == "wamid.message-1"
    assert messages[0].from_number == "15551234567"
    assert messages[0].display_name == "Enterprise Buyer"
    assert messages[0].text == "Need 500 wireless earphones"


@pytest.mark.asyncio
async def test_connector_maps_webhook_to_unified_message_protocol() -> None:
    settings = Settings(_env_file=None)
    connector = WhatsAppConnector(
        ConnectorContext(
            tenant_id="tenant-public-id",
            connector_id="connector-public-id",
            config={
                "phone_number_id": "phone-123",
                "business_account_id": "waba-123",
                "access_token": "server-token",
                "verify_token": "verify-token",
                "app_secret": "app-secret",
            },
        ),
        settings,
    )

    envelopes = await connector.normalize_inbound(
        WEBHOOK_PAYLOAD,
        {"x-request-id": "request-1"},
    )

    assert connector_registry.get("whatsapp") is WhatsAppConnector
    assert len(envelopes) == 1
    assert envelopes[0].direction is Direction.INBOUND
    assert envelopes[0].external_message_id == "wamid.message-1"
    assert envelopes[0].sender.id == "15551234567"
    assert isinstance(envelopes[0].content, TextContent)
    assert envelopes[0].content.text == "Need 500 wireless earphones"


@pytest.mark.asyncio
async def test_graph_client_keeps_access_token_in_authorization_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.connectors.whatsapp.client.httpx.AsyncClient",
        FakeAsyncClient,
    )
    client = WhatsAppApiClient(
        Settings(_env_file=None, whatsapp_graph_api_version="v23.0"),
        phone_number_id="phone-123",
        access_token="server-only-token",
    )

    result = await client.send_text("15551234567", "Enterprise reply")

    assert FakeAsyncClient.base_url == "https://graph.facebook.com/v23.0"
    assert FakeAsyncClient.method == "POST"
    assert FakeAsyncClient.path == "phone-123/messages"
    assert FakeAsyncClient.headers == {
        "Authorization": "Bearer server-only-token",
        "Content-Type": "application/json",
    }
    assert "server-only-token" not in str(FakeAsyncClient.request_json)
    assert result.message_id == "wamid.outbound-1"


def test_webhook_signature_uses_meta_app_secret() -> None:
    body = b'{"object":"whatsapp_business_account"}'
    signature = "sha256=" + hmac.new(
        b"app-secret",
        body,
        hashlib.sha256,
    ).hexdigest()

    WhatsAppService._verify_signature(body, signature, "app-secret")

    with pytest.raises(AppError) as exc_info:
        WhatsAppService._verify_signature(body, "sha256=invalid", "app-secret")
    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "WHATSAPP_SIGNATURE_INVALID"


def test_connector_configuration_requires_webhook_security_fields() -> None:
    errors = WhatsAppConnector.validate_config(
        {
            "phone_number_id": "phone-123",
            "business_account_id": "waba-123",
            "access_token": "token",
            "verify_token": "verify",
        }
    )

    assert errors == ["app_secret is required"]
