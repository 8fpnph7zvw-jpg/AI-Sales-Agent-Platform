from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

import pytest

from scripts import test_whatsapp_flow as flow


class FakeResponse:
    def __init__(self, payload: Any) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self.payload


class FakeClient:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str, dict[str, Any]]] = []

    async def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.requests.append(("GET", url, kwargs))
        payload: Any = [{"id": "session-1", "status": "connected"}]
        if url.endswith("/health/ready"):
            payload = {"status": "ready"}
        return FakeResponse(payload)

    async def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.requests.append(("POST", url, kwargs))
        if url.endswith("/chat-messages"):
            return FakeResponse(
                {"answer": "风衣推荐", "conversation_id": "conversation-1"}
            )
        return FakeResponse({"status": "accepted", "messageId": "message-1"})


@pytest.mark.asyncio
async def test_openwa_health_check_reads_service_and_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENWA_URL", "http://openwa:2785/api")
    monkeypatch.setenv("OPENWA_API_KEY", "openwa-key")
    client = FakeClient()

    await flow.check_openwa_health(client)  # type: ignore[arg-type]

    assert [request[:2] for request in client.requests] == [
        ("GET", "http://openwa:2785/api/health/ready"),
        ("GET", "http://openwa:2785/api/sessions"),
    ]


@pytest.mark.asyncio
async def test_send_test_message_uses_existing_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENWA_URL", "http://openwa:2785/api")
    monkeypatch.setenv("OPENWA_API_KEY", "openwa-key")
    monkeypatch.setenv("OPENWA_SESSION", "session-1")
    client = FakeClient()

    await flow.send_test_message(
        client,  # type: ignore[arg-type]
        phone="+86 138 0013 8000",
        message="发送测试",
    )

    method, url, kwargs = client.requests[0]
    assert method == "POST"
    assert url.endswith("/sessions/session-1/messages/send-text")
    assert kwargs["json"] == {
        "chatId": "8613800138000@c.us",
        "text": "发送测试",
    }


@pytest.mark.asyncio
async def test_simulated_webhook_has_valid_openwa_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BACKEND_API_URL", "http://backend:8000/api/v1")
    monkeypatch.setenv("OPENWA_API_KEY", "openwa-key")
    monkeypatch.setenv("OPENWA_SESSION", "session-1")
    client = FakeClient()

    await flow.simulate_webhook(
        client,  # type: ignore[arg-type]
        phone="+86 138 0013 8000",
        message="你好",
    )

    _, url, kwargs = client.requests[0]
    body = kwargs["content"]
    signature = kwargs["headers"]["X-OpenWA-Signature"]
    expected = hmac.new(b"openwa-key", body, hashlib.sha256).hexdigest()
    assert url.endswith("/webhooks/whatsapp")
    assert signature == f"sha256={expected}"
    assert json.loads(body)["data"]["body"] == "你好"


@pytest.mark.asyncio
async def test_dify_check_uses_app_api_chat_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DIFY_API_BASE_URL", "https://api.dify.ai/v1")
    monkeypatch.setenv("DIFY_API_KEY", "app-test-key")
    client = FakeClient()

    await flow.check_dify(client, query="风衣")  # type: ignore[arg-type]

    _, url, kwargs = client.requests[0]
    assert url == "https://api.dify.ai/v1/chat-messages"
    assert kwargs["headers"]["Authorization"] == "Bearer app-test-key"
    assert kwargs["json"]["query"] == "风衣"
