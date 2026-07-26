from __future__ import annotations

import httpx
import pytest

from app.main import create_app

EXPECTED_OPERATIONS = {
    ("/api/v1/auth/login", "post"),
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
