from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from app.connectors.base import ConnectorContext
from app.connectors.whatsapp.client import WhatsAppConnector
from app.connectors.whatsapp.providers.cloud_api import WhatsAppCloudAPIAdapter
from app.core.config import Settings
from app.core.exceptions import AppError
from app.schemas.protocol import Direction, MessageType, Party, TextContent, UnifiedMessageEnvelope


def cloud_config() -> dict[str, str]:
    return {
        "adapter": "cloud_api",
        "phone_number_id": "123456789",
        "access_token": "access-token",
        "verify_token": "verify-token",
        "app_secret": "app-secret",
        "graph_api_base_url": "https://graph.facebook.com",
        "graph_api_version": "v23.0",
    }


def test_connector_requires_cloud_api_credentials() -> None:
    errors = WhatsAppConnector.validate_config({"adapter": "cloud_api"})
    assert errors == [
        "phone_number_id is required",
        "access_token is required",
        "verify_token is required",
        "app_secret is required",
    ]


def test_connector_uses_provider_registry() -> None:
    connector = WhatsAppConnector(
        ConnectorContext(
            tenant_id="tenant-1",
            connector_id="connector-1",
            config=cloud_config(),
        ),
        Settings(_env_file=None),
    )
    assert connector.display_name == "WhatsApp Business"
    assert connector.adapter_key == "cloud_api"
    assert isinstance(connector.adapter, WhatsAppCloudAPIAdapter)


@pytest.mark.asyncio
async def test_cloud_api_webhook_is_verified_and_normalized() -> None:
    adapter = WhatsAppCloudAPIAdapter(cloud_config())
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {"phone_number_id": "123456789"},
                            "contacts": [
                                {"wa_id": "8613800138000", "profile": {"name": "Buyer"}}
                            ],
                            "messages": [
                                {
                                    "id": "wamid.message-1",
                                    "from": "8613800138000",
                                    "timestamp": "1785376800",
                                    "type": "text",
                                    "text": {"body": "Hello"},
                                }
                            ],
                        },
                    }
                ]
            }
        ],
    }
    raw_body = json.dumps(payload, separators=(",", ":")).encode()
    digest = hmac.new(b"app-secret", raw_body, hashlib.sha256).hexdigest()
    envelopes = await adapter.normalize_inbound(
        payload,
        {"x-hub-signature-256": f"sha256={digest}"},
        raw_body,
        tenant_id="tenant-1",
        connector_id="connector-1",
    )
    assert len(envelopes) == 1
    assert envelopes[0].external_message_id == "wamid.message-1"
    assert envelopes[0].sender.id == "8613800138000"
    assert envelopes[0].sender.display_name == "Buyer"
    assert envelopes[0].content == TextContent(text="Hello")
    assert envelopes[0].context.attributes["provider"] == "cloud_api"


@pytest.mark.asyncio
async def test_cloud_api_rejects_invalid_signature() -> None:
    adapter = WhatsAppCloudAPIAdapter(cloud_config())
    with pytest.raises(AppError, match="invalid"):
        await adapter.normalize_inbound(
            {"object": "whatsapp_business_account"},
            {"x-hub-signature-256": "sha256=invalid"},
            b"{}",
            tenant_id="tenant-1",
            connector_id="connector-1",
        )


def test_cloud_api_verification_challenge() -> None:
    adapter = WhatsAppCloudAPIAdapter(cloud_config())
    assert adapter.verify_challenge("subscribe", "verify-token", "challenge") == "challenge"
    with pytest.raises(AppError):
        adapter.verify_challenge("subscribe", "wrong", "challenge")


@pytest.mark.asyncio
async def test_cloud_api_send_uses_normalized_message(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = WhatsAppCloudAPIAdapter(cloud_config())
    captured: dict[str, object] = {}

    async def fake_request(method: str, path: str, **kwargs: object) -> dict[str, object]:
        captured.update({"method": method, "path": path, **kwargs})
        return {"messages": [{"id": "wamid.outbound-1"}]}

    monkeypatch.setattr(adapter, "_request", fake_request)
    message = UnifiedMessageEnvelope(
        idempotency_key="whatsapp:test:outbound-1",
        tenant_id="tenant-1",
        channel="whatsapp",
        direction=Direction.OUTBOUND,
        message_type=MessageType.TEXT,
        conversation_id="conversation-1",
        sender=Party(id="123456789"),
        recipients=[Party(id="+86 138-0013-8000")],
        content=TextContent(text="Reply"),
    )
    result = await adapter.send(message)
    assert result.accepted is True
    assert result.provider_request_id == "wamid.outbound-1"
    assert captured["path"] == "123456789/messages"
    assert captured["json"] == {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": "8613800138000",
        "type": "text",
        "text": {"body": "Reply"},
    }
