from __future__ import annotations

import hashlib
import hmac
from types import SimpleNamespace
from typing import Any

import pytest

from app.connectors.base import ConnectorContext
from app.connectors.registry import connector_registry
from app.connectors.whatsapp.client import OpenWAClient, WhatsAppConnector
from app.connectors.whatsapp.schemas import (
    OpenWASessionStatusResponse,
    OpenWAStatusWebhookPayload,
    WhatsAppSendRequest,
    WhatsAppWebhookPayload,
    parse_inbound_messages,
)
from app.connectors.whatsapp.service import WhatsAppService
from app.core.config import Settings
from app.core.exceptions import AppError
from app.schemas.protocol import Direction, TextContent

WEBHOOK_PAYLOAD = {
    "event": "message.received",
    "timestamp": "2026-07-28T10:00:00.000Z",
    "sessionId": "sales-bot",
    "idempotencyKey": "msg_sales-bot_ABCD1234",
    "deliveryId": "dlv_550e8400-e29b-41d4-a716-446655440000",
    "data": {
        "id": "ABCD1234",
        "from": "15551234567@c.us",
        "to": "15550001111@c.us",
        "body": "Need 500 wireless earphones",
        "type": "text",
        "timestamp": 1710000000,
        "hasMedia": False,
        "contact": {"id": "15551234567@c.us", "name": "Enterprise Buyer"},
    },
}


def test_send_request_uses_phone_and_message_with_legacy_compatibility() -> None:
    current = WhatsAppSendRequest.model_validate(
        {"phone": "+1 555 123 4567", "message": "Hello"}
    )
    legacy = WhatsAppSendRequest.model_validate(
        {"recipient": "+1 555 123 4567", "text": "Hello"}
    )

    assert current == legacy
    assert current.model_dump(by_alias=True) == {
        "phone": "+1 555 123 4567",
        "message": "Hello",
    }


class FakeResponse:
    status_code = 201

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return {"messageId": "wamid.outbound-1", "timestamp": 1710000001}


class FakeSessionListResponse(FakeResponse):
    def json(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "6b1d329f-ba60-4eda-b28a-6116d70f9b35",
                "name": "sales-bot",
                "status": "ready",
            }
        ]


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
        if method == "GET" and path == "sessions":
            return FakeSessionListResponse()
        return FakeResponse()


class SequenceResponse:
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self.payload


class SequenceAsyncClient:
    responses: list[SequenceResponse] = []
    requests: list[tuple[str, str, dict[str, Any] | None]] = []

    def __init__(self, *, base_url: str, timeout: float) -> None:
        del base_url, timeout

    async def __aenter__(self) -> SequenceAsyncClient:
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
    ) -> SequenceResponse:
        del headers
        type(self).requests.append((method, path, kwargs.get("json")))
        return type(self).responses.pop(0)


def test_openwa_payload_is_normalized_without_losing_provider_identity() -> None:
    parsed = WhatsAppWebhookPayload.model_validate(WEBHOOK_PAYLOAD)

    messages = parse_inbound_messages(parsed)

    assert parsed.session_id == "sales-bot"
    assert len(messages) == 1
    assert messages[0].message_id == "ABCD1234"
    assert messages[0].from_number == "15551234567@c.us"
    assert messages[0].display_name == "Enterprise Buyer"
    assert messages[0].text == "Need 500 wireless earphones"


@pytest.mark.parametrize("upstream_status", ["ready", "connected", "authenticated"])
def test_openwa_logged_in_statuses_are_connected(upstream_status: str) -> None:
    assert OpenWAClient.normalize_status(upstream_status) == "connected"
    assert OpenWAClient.normalize_status(upstream_status.upper()) == "connected"


def test_openwa_waiting_qr_is_only_mapped_from_qr_states() -> None:
    assert OpenWAClient.normalize_status("waiting_qr") == "waiting_qr"
    assert OpenWAClient.normalize_status("qr") == "waiting_qr"
    assert OpenWAClient.normalize_status("authenticated") != "waiting_qr"


def test_openwa_status_webhook_payload_and_connector_sync() -> None:
    payload = OpenWAStatusWebhookPayload.model_validate(
        {
            "event": "authenticated",
            "timestamp": "2026-07-29T10:00:00Z",
            "sessionId": "6bba5383-bf1f-42ce-945f-c5f8920150b8",
            "deliveryId": "delivery-1",
            "status": "connected",
            "phoneNumber": "15551234567",
        }
    )
    connector = SimpleNamespace(
        session_id=None,
        phone=None,
        status="draft",
        health_status=None,
        health_detail=None,
        last_health_check_at=None,
        last_connected_at=None,
        last_disconnect_reason="old disconnect",
    )
    whatsapp_session = SimpleNamespace(
        session_id=None,
        session_name="tenant-sales",
        phone=None,
        status="waiting_qr",
        last_error=None,
        session_data=None,
        qr_code="data:image/png;base64,old",
        last_connected_at=None,
    )
    result = OpenWASessionStatusResponse(
        session_id=payload.session_id,
        name=whatsapp_session.session_name,
        status=OpenWAClient.normalize_status(payload.event),
        api_key_configured=True,
        phone_number=payload.phone_number,
    )

    WhatsAppService._apply_session_status(connector, whatsapp_session, result)

    assert whatsapp_session.status == "connected"
    assert whatsapp_session.qr_code is None
    assert connector.status == "active"
    assert connector.session_id == payload.session_id
    assert connector.phone == "15551234567"
    assert connector.last_connected_at is not None
    assert connector.last_disconnect_reason is None


@pytest.mark.asyncio
async def test_connector_maps_openwa_webhook_to_unified_message_protocol() -> None:
    settings = Settings(
        _env_file=None,
        openwa_api_key="server-key",
        openwa_session="sales-bot",
    )
    connector = WhatsAppConnector(
        ConnectorContext(
            tenant_id="tenant-public-id",
            connector_id="connector-public-id",
            config={"session_id": "sales-bot"},
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
    assert envelopes[0].external_message_id == "ABCD1234"
    assert envelopes[0].sender.id == "15551234567@c.us"
    assert isinstance(envelopes[0].content, TextContent)
    assert envelopes[0].content.text == "Need 500 wireless earphones"


@pytest.mark.asyncio
async def test_openwa_client_keeps_api_key_in_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.connectors.whatsapp.client.httpx.AsyncClient",
        FakeAsyncClient,
    )
    client = OpenWAClient(
        Settings(
            _env_file=None,
            openwa_url="http://openwa:2785/api",
            openwa_api_key="server-only-key",
            openwa_session_name="sales-bot",
        )
    )

    result = await client.send_text("+1 (555) 123-4567", "Enterprise reply")

    assert FakeAsyncClient.base_url == "http://openwa:2785/api/"
    assert FakeAsyncClient.method == "POST"
    assert (
        FakeAsyncClient.path
        == "sessions/6b1d329f-ba60-4eda-b28a-6116d70f9b35/messages/send-text"
    )
    assert FakeAsyncClient.headers == {
        "x-api-key": "server-only-key",
        "Content-Type": "application/json",
    }
    assert FakeAsyncClient.request_json == {
        "chatId": "15551234567@c.us",
        "text": "Enterprise reply",
    }
    assert "server-only-key" not in str(FakeAsyncClient.request_json)
    assert result.message_id == "wamid.outbound-1"


@pytest.mark.asyncio
async def test_openwa_session_flow_creates_starts_and_keeps_name_in_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.connectors.whatsapp.client.httpx.AsyncClient",
        SequenceAsyncClient,
    )
    SequenceAsyncClient.requests = []
    SequenceAsyncClient.responses = [
        SequenceResponse(200, []),
        SequenceResponse(
            201,
            {
                "id": "6b1d329f-ba60-4eda-b28a-6116d70f9b35",
                "name": "ai-sales-agent",
                "status": "created",
            },
        ),
        SequenceResponse(
            200,
            {
                "id": "6b1d329f-ba60-4eda-b28a-6116d70f9b35",
                "name": "ai-sales-agent",
                "status": "initializing",
            },
        ),
    ]
    client = OpenWAClient(
        Settings(
            _env_file=None,
            openwa_api_key="server-only-key",
            openwa_session="6b1d329f-ba60-4eda-b28a-6116d70f9b35",
            openwa_session_name="ai-sales-agent",
        )
    )

    result = await client.create_session()

    assert result.session_id == "6b1d329f-ba60-4eda-b28a-6116d70f9b35"
    assert SequenceAsyncClient.requests == [
        ("GET", "sessions", None),
        ("POST", "sessions", {"name": "ai-sales-agent"}),
        (
            "POST",
            "sessions/6b1d329f-ba60-4eda-b28a-6116d70f9b35/start",
            None,
        ),
    ]


@pytest.mark.asyncio
async def test_openwa_create_conflict_lists_and_reuses_existing_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.connectors.whatsapp.client.httpx.AsyncClient",
        SequenceAsyncClient,
    )
    session_id = "6b1d329f-ba60-4eda-b28a-6116d70f9b35"
    existing = {
        "id": session_id,
        "name": "ai-sales-agent",
        "status": "created",
    }
    SequenceAsyncClient.requests = []
    SequenceAsyncClient.responses = [
        SequenceResponse(200, []),
        SequenceResponse(409, {"error": "Session name already exists"}),
        SequenceResponse(200, [existing]),
        SequenceResponse(200, {**existing, "status": "initializing"}),
    ]
    client = OpenWAClient(
        Settings(
            _env_file=None,
            openwa_api_key="server-only-key",
            openwa_session_name="ai-sales-agent",
        )
    )

    result = await client.create_session()

    assert result.session_id == session_id
    assert result.status == "starting"
    assert SequenceAsyncClient.requests == [
        ("GET", "sessions", None),
        ("POST", "sessions", {"name": "ai-sales-agent"}),
        ("GET", "sessions", None),
        ("POST", f"sessions/{session_id}/start", None),
    ]


@pytest.mark.asyncio
async def test_openwa_existing_session_continues_after_start_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.connectors.whatsapp.client.httpx.AsyncClient",
        SequenceAsyncClient,
    )
    existing = {
        "name": "ai-sales-agent",
        "status": "ready",
        "phone": "15551234567",
    }
    SequenceAsyncClient.requests = []
    SequenceAsyncClient.responses = [
        SequenceResponse(
            200,
            [
                {
                    "id": "6b1d329f-ba60-4eda-b28a-6116d70f9b35",
                    **existing,
                }
            ],
        ),
    ]
    client = OpenWAClient(
        Settings(
            _env_file=None,
            openwa_api_key="server-only-key",
            openwa_session_name="ai-sales-agent",
        )
    )

    result = await client.create_session()

    assert result.status == "connected"
    assert result.phone_number == "15551234567"
    assert ("POST", "sessions", {"name": "ai-sales-agent"}) not in (
        SequenceAsyncClient.requests
    )
    assert SequenceAsyncClient.requests == [
        ("GET", "sessions", None),
    ]


@pytest.mark.asyncio
async def test_openwa_qrcode_waits_until_data_url_is_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.connectors.whatsapp.client.httpx.AsyncClient",
        SequenceAsyncClient,
    )
    monkeypatch.setattr("app.connectors.whatsapp.client.asyncio.sleep", _no_sleep)
    session_id = "6b1d329f-ba60-4eda-b28a-6116d70f9b35"
    existing = {
        "id": session_id,
        "name": "ai-sales-agent",
        "status": "created",
    }
    SequenceAsyncClient.requests = []
    SequenceAsyncClient.responses = [
        SequenceResponse(200, [existing]),
        SequenceResponse(200, {**existing, "status": "initializing"}),
        SequenceResponse(200, {**existing, "status": "qr_ready"}),
        SequenceResponse(
            200,
            {
                "qrCode": "data:image/png;base64,qr-data",
                "status": "qr_ready",
            },
        ),
    ]
    client = OpenWAClient(
        Settings(
            _env_file=None,
            openwa_api_key="server-only-key",
            openwa_session_name="ai-sales-agent",
        )
    )

    result = await client.qrcode()

    assert result.session_id == session_id
    assert result.data_url == "data:image/png;base64,qr-data"
    assert SequenceAsyncClient.requests == [
        ("GET", "sessions", None),
        ("POST", f"sessions/{session_id}/start", None),
        ("GET", f"sessions/{session_id}", None),
        ("GET", f"sessions/{session_id}/qr", None),
    ]


@pytest.mark.asyncio
async def test_openwa_qrcode_returns_friendly_starting_state_when_not_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.connectors.whatsapp.client.httpx.AsyncClient",
        SequenceAsyncClient,
    )
    monkeypatch.setattr("app.connectors.whatsapp.client.asyncio.sleep", _no_sleep)
    session_id = "6b1d329f-ba60-4eda-b28a-6116d70f9b35"
    starting = {
        "id": session_id,
        "name": "ai-sales-agent",
        "status": "initializing",
    }
    SequenceAsyncClient.requests = []
    SequenceAsyncClient.responses = [
        SequenceResponse(200, [starting]),
        SequenceResponse(200, starting),
        SequenceResponse(200, starting),
        SequenceResponse(200, [starting]),
    ]
    client = OpenWAClient(
        Settings(
            _env_file=None,
            openwa_api_key="server-only-key",
            openwa_session_name="ai-sales-agent",
            whatsapp_timeout_seconds=1,
        )
    )

    result = await client.qrcode()

    assert result.session_id == session_id
    assert result.status == "starting"
    assert result.data_url is None
    assert "not ready" in result.message
    assert all(not path.endswith("/qr") for _, path, _ in SequenceAsyncClient.requests)


@pytest.mark.asyncio
async def test_openwa_reconnect_preserves_the_existing_session_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.connectors.whatsapp.client.httpx.AsyncClient",
        SequenceAsyncClient,
    )
    session_id = "6b1d329f-ba60-4eda-b28a-6116d70f9b35"
    existing = {
        "id": session_id,
        "name": "ai-sales-agent",
        "status": "disconnected",
    }
    SequenceAsyncClient.requests = []
    SequenceAsyncClient.responses = [
        SequenceResponse(200, [existing]),
        SequenceResponse(202, {**existing, "status": "reconnecting"}),
    ]
    client = OpenWAClient(
        Settings(
            _env_file=None,
            openwa_api_key="server-only-key",
            openwa_session_name="ai-sales-agent",
        )
    )

    result = await client.reconnect()

    assert result.session_id == session_id
    assert result.status == "starting"
    assert SequenceAsyncClient.requests == [
        ("GET", "sessions", None),
        ("POST", f"sessions/{session_id}/reconnect", None),
    ]
    assert all(method != "DELETE" for method, _, _ in SequenceAsyncClient.requests)


@pytest.mark.asyncio
async def test_openwa_reconnect_falls_back_to_start_without_deleting_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.connectors.whatsapp.client.httpx.AsyncClient",
        SequenceAsyncClient,
    )
    session_id = "6bba5383-bf1f-42ce-945f-c5f8920150b8"
    existing = {
        "id": session_id,
        "name": "ai-sales-agent",
        "status": "disconnected",
    }
    SequenceAsyncClient.requests = []
    SequenceAsyncClient.responses = [
        SequenceResponse(200, [existing]),
        SequenceResponse(404, {"error": "route not found"}),
        SequenceResponse(202, {**existing, "status": "initializing"}),
    ]
    client = OpenWAClient(
        Settings(
            _env_file=None,
            openwa_api_key="server-only-key",
            openwa_session_name="ai-sales-agent",
        )
    )

    result = await client.reconnect()

    assert result.session_id == session_id
    assert result.status == "starting"
    assert SequenceAsyncClient.requests == [
        ("GET", "sessions", None),
        ("POST", f"sessions/{session_id}/reconnect", None),
        ("POST", f"sessions/{session_id}/start", None),
    ]
    assert all(method != "DELETE" for method, _, _ in SequenceAsyncClient.requests)


@pytest.mark.asyncio
async def test_openwa_delete_session_is_idempotent_and_uses_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.connectors.whatsapp.client.httpx.AsyncClient",
        SequenceAsyncClient,
    )
    SequenceAsyncClient.requests = []
    SequenceAsyncClient.responses = [
        SequenceResponse(
            200,
            [
                {
                    "id": "6b1d329f-ba60-4eda-b28a-6116d70f9b35",
                    "name": "ai-sales-agent",
                    "status": "disconnected",
                }
            ],
        ),
        SequenceResponse(204, {}),
    ]
    client = OpenWAClient(
        Settings(
            _env_file=None,
            openwa_api_key="server-only-key",
            openwa_session_name="ai-sales-agent",
        )
    )

    result = await client.delete_session()

    assert result.status == "disconnected"
    assert SequenceAsyncClient.requests == [
        ("GET", "sessions", None),
        (
            "DELETE",
            "sessions/6b1d329f-ba60-4eda-b28a-6116d70f9b35",
            None,
        ),
    ]


@pytest.mark.asyncio
async def _no_sleep(_: float) -> None:
    return None


def test_webhook_signature_uses_openwa_api_key() -> None:
    body = b'{"event":"message.received"}'
    signature = "sha256=" + hmac.new(
        b"openwa-api-key",
        body,
        hashlib.sha256,
    ).hexdigest()

    WhatsAppService._verify_signature(body, signature, "openwa-api-key")

    with pytest.raises(AppError) as exc_info:
        WhatsAppService._verify_signature(body, "sha256=invalid", "openwa-api-key")
    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "WHATSAPP_SIGNATURE_INVALID"


def test_connector_configuration_requires_session_id() -> None:
    errors = WhatsAppConnector.validate_config({})

    assert errors == ["session_id is required"]
