from __future__ import annotations

from typing import Any

import pytest

from app.core.config import Settings
from app.integrations.dify.client import DifyClient


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return {
            "answer": "Enterprise response",
            "conversation_id": "dify-conversation",
            "task_id": "dify-task",
            "message_id": "dify-message",
            "metadata": {
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_price": "0.0015",
                    "currency": "USD",
                    "latency": 0.25,
                },
                "retriever_resources": [{"document_name": "catalog.pdf"}],
            },
        }


class FakeAsyncClient:
    request_path: str | None = None
    request_json: dict[str, Any] | None = None
    request_headers: dict[str, str] | None = None
    base_url: str | None = None

    def __init__(self, *, base_url: str, timeout: float) -> None:
        type(self).base_url = base_url

    async def __aenter__(self) -> FakeAsyncClient:
        return self

    async def __aexit__(self, *args) -> None:
        return None

    async def post(
        self,
        path: str,
        *,
        json: dict[str, Any],
        headers: dict[str, str],
    ) -> FakeResponse:
        type(self).request_path = path
        type(self).request_json = json
        type(self).request_headers = headers
        return FakeResponse()


@pytest.mark.asyncio
async def test_dify_chat_uses_server_side_key_and_v1_relative_path(monkeypatch) -> None:
    monkeypatch.setattr("app.integrations.dify.client.httpx.AsyncClient", FakeAsyncClient)
    settings = Settings(
        _env_file=None,
        dify_api_base_url="https://api.dify.ai/v1",
        dify_api_key="server-only-key",
    )

    result = await DifyClient(settings).chat(
        query="Need 500 units",
        user="tenant:t:customer:c",
        conversation_id=None,
        inputs={"language": "en"},
    )

    assert FakeAsyncClient.base_url == "https://api.dify.ai/v1"
    assert FakeAsyncClient.request_path == "chat-messages"
    assert FakeAsyncClient.request_headers == {
        "Authorization": "Bearer server-only-key",
        "Content-Type": "application/json",
    }
    assert FakeAsyncClient.request_json["response_mode"] == "blocking"
    assert result.answer == "Enterprise response"
    assert result.prompt_tokens == 10
    assert result.latency_ms == 250
