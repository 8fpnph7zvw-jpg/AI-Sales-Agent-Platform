from __future__ import annotations

import json
import logging
from typing import Any

import httpx
import pytest

from app.core.config import Settings
from app.integrations.feishu.client import FeishuClient
from app.integrations.feishu.exceptions import FeishuAPIError
from app.integrations.feishu.schemas import FeishuSendResult
from app.integrations.feishu.service import FeishuService


class FakeAsyncClient:
    def __init__(
        self,
        responses: list[httpx.Response],
        calls: list[dict[str, Any]],
    ) -> None:
        self.responses = responses
        self.calls = calls

    async def __aenter__(self) -> FakeAsyncClient:
        return self

    async def __aexit__(self, *_args: Any) -> None:
        return None

    async def post(self, path: str, **kwargs: Any) -> httpx.Response:
        self.calls.append({"path": path, **kwargs})
        return self.responses.pop(0)


def response(status_code: int, body: dict[str, Any]) -> httpx.Response:
    request = httpx.Request("POST", "https://open.feishu.cn/test")
    return httpx.Response(status_code, json=body, request=request)


def settings() -> Settings:
    return Settings(
        _env_file=None,
        feishu_enabled=True,
        feishu_app_id="cli_test_app_id",
        feishu_app_secret="cli_test_app_secret",
    )


def install_fake_client(
    monkeypatch: pytest.MonkeyPatch,
    responses: list[httpx.Response],
) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "app.integrations.feishu.client.httpx.AsyncClient",
        lambda **_kwargs: FakeAsyncClient(responses, calls),
    )
    return calls


@pytest.mark.asyncio
async def test_tenant_token_is_fetched_and_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = install_fake_client(
        monkeypatch,
        [response(200, {"code": 0, "msg": "ok", "tenant_access_token": "token-1", "expire": 7200})],
    )
    client = FeishuClient(settings())

    first = await client.get_tenant_access_token()
    second = await client.get_tenant_access_token()

    assert first == second == "token-1"
    assert [call["path"] for call in calls] == [
        "open-apis/auth/v3/tenant_access_token/internal"
    ]


@pytest.mark.asyncio
async def test_text_message_uses_open_id_and_cached_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = install_fake_client(
        monkeypatch,
        [
            response(200, {"code": 0, "tenant_access_token": "token-1", "expire": 7200}),
            response(200, {"code": 0, "msg": "ok", "data": {"message_id": "om_123"}}),
        ],
    )
    client = FeishuClient(settings())

    result = await client.send_text_message("ou_receiver", "测试消息")

    assert result.message_id == "om_123"
    message_call = calls[1]
    assert message_call["path"] == "open-apis/im/v1/messages"
    assert message_call["params"] == {"receive_id_type": "open_id"}
    assert message_call["headers"] == {"Authorization": "Bearer token-1"}
    assert message_call["json"]["receive_id"] == "ou_receiver"
    assert json.loads(message_call["json"]["content"]) == {"text": "测试消息"}


@pytest.mark.asyncio
async def test_invalid_token_refreshes_and_retries_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = install_fake_client(
        monkeypatch,
        [
            response(200, {"code": 0, "tenant_access_token": "token-1", "expire": 7200}),
            response(200, {"code": 99991663, "msg": "token invalid"}),
            response(200, {"code": 0, "tenant_access_token": "token-2", "expire": 7200}),
            response(200, {"code": 0, "data": {"message_id": "om_456"}}),
        ],
    )
    client = FeishuClient(settings())

    result = await client.send_text_message("ou_receiver", "hello")

    assert result.message_id == "om_456"
    assert [call["path"] for call in calls].count(
        "open-apis/auth/v3/tenant_access_token/internal"
    ) == 2
    assert calls[-1]["headers"] == {"Authorization": "Bearer token-2"}


@pytest.mark.asyncio
async def test_token_api_error_raises_feishu_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fake_client(
        monkeypatch,
        [response(200, {"code": 10003, "msg": "invalid app credentials"})],
    )
    client = FeishuClient(settings())

    with pytest.raises(FeishuAPIError) as error:
        await client.get_tenant_access_token()

    assert error.value.code == "FEISHU_TOKEN_REQUEST_FAILED"


@pytest.mark.asyncio
async def test_http_error_raises_feishu_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fake_client(
        monkeypatch,
        [response(500, {"code": 500, "msg": "server error"})],
    )
    client = FeishuClient(settings())

    with pytest.raises(FeishuAPIError) as error:
        await client.get_tenant_access_token()

    assert error.value.upstream_status_code == 500


class StubFeishuClient:
    configured = True

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    async def send_text_message(
        self,
        receiver_open_id: str,
        content: str,
    ) -> FeishuSendResult:
        assert receiver_open_id == "ou_receiver"
        assert content == "test message"
        if self.fail:
            raise FeishuAPIError("message rejected")
        return FeishuSendResult(message_id="om_789")


@pytest.mark.asyncio
async def test_service_logs_message_context(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = FeishuService(StubFeishuClient())  # type: ignore[arg-type]
    caplog.set_level(logging.INFO)

    result = await service.send_text_message(
        "ou_receiver",
        "test message",
        customer_id="customer-1",
        user_id="user-1",
    )

    assert result.message_id == "om_789"
    assert "feishu_message_send_started customer_id=customer-1 user_id=user-1" in caplog.text
    assert "feishu_message_send_success customer_id=customer-1 user_id=user-1" in caplog.text


@pytest.mark.asyncio
async def test_service_logs_message_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = FeishuService(StubFeishuClient(fail=True))  # type: ignore[arg-type]
    caplog.set_level(logging.INFO)

    with pytest.raises(FeishuAPIError):
        await service.send_text_message(
            "ou_receiver",
            "test message",
            customer_id="customer-1",
            user_id="user-1",
        )

    assert "feishu_message_send_failed customer_id=customer-1 user_id=user-1" in caplog.text
