from __future__ import annotations

import httpx
import pytest

from app.main import create_app

EXPECTED_OPERATIONS = {
    ("/api/v1/auth/login", "post"),
    ("/api/v1/auth/me", "get"),
    ("/api/v1/customers", "get"),
    ("/api/v1/customers", "post"),
    ("/api/v1/conversations", "get"),
    ("/api/v1/conversations", "post"),
    ("/api/v1/conversations/{conversation_id}/messages", "get"),
    ("/api/v1/conversation/message", "post"),
    ("/api/v1/agent/chat", "post"),
    ("/api/v1/lead-score", "post"),
    ("/api/v1/quotation", "post"),
    ("/api/v1/quotations", "get"),
    ("/api/v1/products", "get"),
    ("/api/v1/connectors", "get"),
    ("/api/v1/connectors/config", "post"),
    ("/api/v1/connectors/whatsapp/{connector_id}/config-status", "get"),
    ("/api/v1/connectors/whatsapp/test", "post"),
    ("/api/v1/webhooks/whatsapp", "get"),
    ("/api/v1/webhooks/whatsapp", "post"),
    ("/api/v1/whatsapp/send", "post"),
    ("/api/v1/notifications/send", "post"),
    ("/api/v1/workflows", "get"),
}


def test_openapi_exposes_required_rest_operations() -> None:
    schema = create_app().openapi()
    operations = {
        (path, method) for path, path_item in schema["paths"].items() for method in path_item
    }
    assert EXPECTED_OPERATIONS <= operations


@pytest.mark.asyncio
async def test_protected_endpoint_requires_bearer_token() -> None:
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/v1/customers")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_FAILED"
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.asyncio
async def test_liveness_endpoint_is_public() -> None:
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_invalid_whatsapp_webhook_payload_is_rejected_without_auth() -> None:
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/api/v1/webhooks/whatsapp", json={})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "WHATSAPP_PAYLOAD_INVALID"


@pytest.mark.asyncio
async def test_openwa_webhook_requires_hmac_signature() -> None:
    app = create_app()
    payload = {
        "event": "message.received",
        "timestamp": "2026-07-28T10:00:00.000Z",
        "sessionId": "sales-bot",
        "idempotencyKey": "msg_sales-bot_ABCD1234",
        "deliveryId": "dlv_550e8400-e29b-41d4-a716-446655440000",
        "data": {
            "id": "ABCD1234",
            "from": "15551234567@c.us",
            "body": "hello",
            "type": "text",
            "timestamp": 1710000000,
        },
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/api/v1/webhooks/whatsapp", json=payload)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "OPENWA_API_KEY_REQUIRED"


@pytest.mark.asyncio
async def test_whatsapp_test_endpoint_requires_bearer_token() -> None:
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/connectors/whatsapp/test",
            json={"connector_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV"},
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_FAILED"


@pytest.mark.asyncio
async def test_whatsapp_send_endpoint_requires_bearer_token() -> None:
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/whatsapp/send",
            json={"recipient": "15551234567", "text": "hello"},
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_FAILED"
