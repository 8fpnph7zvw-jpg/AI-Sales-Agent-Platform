from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.core.config import Settings
from app.core.exceptions import ServiceConfigurationError, UpstreamServiceError
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


class UnauthorizedAsyncClient(FakeAsyncClient):
    async def post(
        self,
        path: str,
        *,
        json: dict[str, Any],
        headers: dict[str, str],
    ) -> httpx.Response:
        del json, headers
        request = httpx.Request("POST", f"https://api.dify.ai/v1/{path}")
        return httpx.Response(401, request=request, json={"message": "Unauthorized"})


class BadRequestAsyncClient(FakeAsyncClient):
    async def post(
        self,
        path: str,
        *,
        json: dict[str, Any],
        headers: dict[str, str],
    ) -> httpx.Response:
        del json, headers
        request = httpx.Request("POST", f"https://api.dify.ai/v1/{path}")
        return httpx.Response(
            400,
            request=request,
            json={"code": "invalid_param", "message": "unexpected inputs"},
        )


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

    assert FakeAsyncClient.base_url == "https://api.dify.ai/v1/"
    assert FakeAsyncClient.request_path == "chat-messages"
    assert FakeAsyncClient.request_headers == {
        "Authorization": "Bearer server-only-key",
        "Content-Type": "application/json",
    }
    assert FakeAsyncClient.request_json == {
        "inputs": {},
        "query": "Need 500 units",
        "response_mode": "blocking",
        "conversation_id": "",
        "user": "tenant:t:customer:c",
    }
    assert result.answer == "Enterprise response"
    assert result.prompt_tokens == 10
    assert result.latency_ms == 250


@pytest.mark.asyncio
async def test_dify_401_reports_app_api_key_requirement(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.integrations.dify.client.httpx.AsyncClient",
        UnauthorizedAsyncClient,
    )
    client = DifyClient(
        Settings(
            _env_file=None,
            dify_api_base_url="https://api.dify.ai/v1",
            dify_api_key="app-invalid-key",
        )
    )

    with pytest.raises(UpstreamServiceError) as exc_info:
        await client.chat(
            query="风衣",
            user="test-user",
            conversation_id=None,
            inputs={},
        )

    assert "HTTP 401" in exc_info.value.message
    assert "App API key" in exc_info.value.message


@pytest.mark.asyncio
async def test_dify_dataset_key_is_rejected_before_chat_request() -> None:
    client = DifyClient(
        Settings(
            _env_file=None,
            dify_api_key="dataset-not-an-app-key",
        )
    )

    with pytest.raises(ServiceConfigurationError) as exc_info:
        await client.chat(
            query="风衣",
            user="test-user",
            conversation_id=None,
            inputs={},
        )

    assert "Dataset/Knowledge" in exc_info.value.message


@pytest.mark.asyncio
async def test_dify_400_logs_status_and_response_text(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(
        "app.integrations.dify.client.httpx.AsyncClient",
        BadRequestAsyncClient,
    )
    client = DifyClient(
        Settings(
            _env_file=None,
            dify_api_base_url="https://api.dify.ai/v1",
            dify_api_key="app-test-key",
        )
    )

    with pytest.raises(UpstreamServiceError):
        await client.chat(
            query="风衣",
            user="customer-id",
            conversation_id="old-conversation-id",
            inputs={"customer_message": "风衣"},
        )

    assert "status_code=400" in caplog.text
    assert "unexpected inputs" in caplog.text
