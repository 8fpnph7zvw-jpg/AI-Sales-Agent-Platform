from __future__ import annotations

import httpx
import pytest

from app.api.dependencies.auth import Principal, get_current_principal
from app.core.config import get_settings
from app.main import create_app
from app.modules.ai_agent.router import get_ai_agent_service
from app.modules.ai_agent.schemas import AgentChatResponse, AgentUsage

EXPECTED_OPERATIONS = {
    ("/api/v1/auth/login", "post"),
    ("/api/v1/auth/me", "get"),
    ("/api/v1/customers", "get"),
    ("/api/v1/customers", "post"),
    ("/api/v1/customers/{customer_id}", "get"),
    ("/api/v1/customers/{customer_id}", "patch"),
    ("/api/v1/customers/{customer_id}", "delete"),
    ("/api/v1/customers/{customer_id}/owner", "patch"),
    ("/api/v1/conversations", "get"),
    ("/api/v1/conversations", "post"),
    ("/api/v1/conversations/{conversation_id}", "delete"),
    ("/api/v1/conversations/{conversation_id}/messages", "get"),
    ("/api/v1/conversations/message", "post"),
    ("/api/v1/conversations/session-status", "post"),
    ("/api/v1/conversation/message", "post"),
    ("/api/v1/agent/chat", "post"),
    ("/api/v1/lead-score", "post"),
    ("/api/v1/lead-scores", "get"),
    ("/api/v1/lead-scores/run", "post"),
    ("/api/v1/users", "get"),
    ("/api/v1/users", "post"),
    ("/api/v1/users/{user_id}", "patch"),
    ("/api/v1/users/{user_id}", "delete"),
    ("/api/v1/quotation", "post"),
    ("/api/v1/quotations", "get"),
    ("/api/v1/quotations/{quotation_id}/status", "patch"),
    ("/api/v1/quotations/{quotation_id}", "delete"),
    ("/api/v1/products", "get"),
    ("/api/v1/connectors", "get"),
    ("/api/v1/connectors/config", "post"),
    ("/api/v1/connectors/whatsapp/{connector_id}/config-status", "get"),
    ("/api/v1/connectors/whatsapp/{connector_id}/web-session/connect", "post"),
    ("/api/v1/connectors/whatsapp/{connector_id}/web-session/status", "get"),
    ("/api/v1/connectors/whatsapp/{connector_id}/web-session/qr", "get"),
    ("/api/v1/connectors/whatsapp/{connector_id}/web-session/reconnect", "post"),
    ("/api/v1/connectors/whatsapp/{connector_id}/web-session", "delete"),
    ("/api/v1/connectors/whatsapp/test", "post"),
    ("/api/v1/webhooks/whatsapp", "get"),
    ("/api/v1/webhooks/whatsapp/{connector_id}", "get"),
    ("/api/v1/webhooks/whatsapp/{connector_id}", "post"),
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
async def test_agent_chat_endpoint_returns_200() -> None:
    app = create_app()

    class FakeAgentService:
        async def chat(self, principal, payload, *, request_id=None) -> AgentChatResponse:
            assert principal.tenant_id == 1
            assert payload.query == "风衣"
            assert request_id == "request-agent-1"
            return AgentChatResponse(
                run_id="01ARZ3NDEKTSV4RRFFQ69G5FA1",
                conversation_id=payload.conversation_id,
                message_id="01ARZ3NDEKTSV4RRFFQ69G5FA2",
                answer="推荐经典风衣",
                dify_conversation_id="dify-conversation",
                citations=[],
                usage=AgentUsage(
                    prompt_tokens=8,
                    completion_tokens=6,
                    cost_amount=None,
                    cost_currency=None,
                    latency_ms=120,
                ),
            )

    async def principal_override() -> Principal:
        return Principal(
            user_id=1,
            user_public_id="01ARZ3NDEKTSV4RRFFQ69G5FA3",
            tenant_id=1,
            tenant_public_id="01ARZ3NDEKTSV4RRFFQ69G5FA4",
            permissions=frozenset({"ai_agent.chat"}),
        )

    async def service_override() -> FakeAgentService:
        return FakeAgentService()

    app.dependency_overrides[get_current_principal] = principal_override
    app.dependency_overrides[get_ai_agent_service] = service_override
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/agent/chat",
            headers={"X-Request-ID": "request-agent-1"},
            json={
                "conversation_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
                "query": "风衣",
                "idempotency_key": "agent-chat-test-001",
            },
        )

    assert response.status_code == 200
    assert response.json()["answer"] == "推荐经典风衣"


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


@pytest.mark.asyncio
async def test_whatsapp_web_session_endpoint_requires_bearer_token() -> None:
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/connectors/whatsapp/01ARZ3NDEKTSV4RRFFQ69G5FAV/web-session/connect"
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_FAILED"


@pytest.mark.asyncio
async def test_whatsapp_gateway_endpoint_rejects_invalid_shared_token(monkeypatch) -> None:
    monkeypatch.setenv("WHATSAPP_GATEWAY_TOKEN", "gateway-secret")
    get_settings.cache_clear()
    try:
        app = create_app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/v1/conversations/message",
                headers={"X-WhatsApp-Gateway-Token": "wrong"},
                json={
                    "phone": "15551234567",
                    "message": "hello",
                    "channel": "whatsapp",
                    "timestamp": 1785376800,
                    "message_id": "webjs-message-1",
                    "session_id": "customer001",
                },
            )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "WHATSAPP_GATEWAY_TOKEN_INVALID"


@pytest.mark.asyncio
async def test_whatsapp_gateway_status_endpoint_rejects_invalid_shared_token(
    monkeypatch,
) -> None:
    monkeypatch.setenv("WHATSAPP_GATEWAY_TOKEN", "gateway-secret")
    get_settings.cache_clear()
    try:
        app = create_app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/v1/conversations/session-status",
                headers={"X-WhatsApp-Gateway-Token": "wrong"},
                json={
                    "session_id": "sales-web-01",
                    "status": "CONNECTED",
                    "phone": "15551234567",
                },
            )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "WHATSAPP_GATEWAY_TOKEN_INVALID"
