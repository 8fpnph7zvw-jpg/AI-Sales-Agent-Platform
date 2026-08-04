from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.api.dependencies.auth import Principal
from app.connectors.feishu.oauth import FeishuOAuthService
from app.core.config import Settings
from app.core.exceptions import AppError, PermissionDeniedError


class FakeSession:
    def __init__(self) -> None:
        self.commit_count = 0
        self.rollback_count = 0

    async def commit(self) -> None:
        self.commit_count += 1

    async def rollback(self) -> None:
        self.rollback_count += 1


class FakeRepository:
    def __init__(self) -> None:
        self.user = SimpleNamespace(
            id=7,
            public_id="01J00000000000000000000007",
            feishu_open_id=None,
            feishu_name=None,
            feishu_bind_status="unbound",
            feishu_bind_time=None,
            phone=None,
        )
        self.oauth_state: Any = None

    async def get_user_by_public_id(self, tenant_id: int, public_id: str) -> Any:
        assert tenant_id == 1
        return self.user if public_id == self.user.public_id else None

    async def get_user(self, tenant_id: int, user_id: int) -> Any:
        assert (tenant_id, user_id) == (1, 7)
        return self.user

    def add_oauth_state(self, oauth_state: Any) -> None:
        self.oauth_state = oauth_state

    async def delete_expired_oauth_states(self, _now: datetime) -> None:
        return None

    async def get_oauth_state_for_update(self, state_hash: str) -> Any:
        if self.oauth_state and self.oauth_state.state_hash == state_hash:
            return self.oauth_state
        return None


class FakeConnectorService:
    async def get_credentials(self, tenant_id: int) -> Any:
        assert tenant_id == 1
        return SimpleNamespace(app_id="cli_enterprise", app_secret="secret-enterprise")


class FakeAsyncClient:
    def __init__(self, calls: list[dict[str, Any]], **_kwargs: Any) -> None:
        self.calls = calls

    async def __aenter__(self) -> FakeAsyncClient:
        return self

    async def __aexit__(self, *_args: Any) -> None:
        return None

    async def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        self.calls.append({"method": method, "path": path, **kwargs})
        request = httpx.Request(method, f"https://open.feishu.cn/{path}")
        if path.endswith("oauth/token"):
            return httpx.Response(
                200,
                json={"code": 0, "access_token": "u-token", "expires_in": 7200},
                request=request,
            )
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "open_id": "ou_sales_01",
                    "name": "张三",
                    "mobile": "+8613800000000",
                },
            },
            request=request,
        )


def settings() -> Settings:
    return Settings(
        _env_file=None,
        feishu_oauth_redirect_uri=(
            "https://sales.example.com/api/v1/connectors/feishu/oauth/callback"
        ),
        frontend_base_url="https://sales.example.com",
        feishu_oauth_state_expire_minutes=10,
    )


def principal(*, permissions: frozenset[str] = frozenset({"user.manage"})) -> Principal:
    return Principal(
        user_id=1,
        user_public_id="01J00000000000000000000001",
        tenant_id=1,
        tenant_public_id="01J00000000000000000000002",
        permissions=permissions,
    )


@pytest.mark.asyncio
async def test_authorization_url_uses_tenant_app_and_pkce() -> None:
    session = FakeSession()
    repository = FakeRepository()
    service = FeishuOAuthService(
        session,  # type: ignore[arg-type]
        repository,  # type: ignore[arg-type]
        FakeConnectorService(),  # type: ignore[arg-type]
        settings(),
    )

    result = await service.authorization_url(principal(), repository.user.public_id)

    query = parse_qs(urlparse(result.url).query)
    assert query["client_id"] == ["cli_enterprise"]
    assert query["response_type"] == ["code"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["redirect_uri"] == [settings().feishu_oauth_redirect_uri]
    assert repository.oauth_state.user_id == 7
    assert repository.oauth_state.initiated_by == 1
    assert repository.oauth_state.code_verifier not in result.url
    assert repository.oauth_state.state_hash == hashlib.sha256(
        query["state"][0].encode()
    ).hexdigest()
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_non_admin_cannot_bind_another_user() -> None:
    service = FeishuOAuthService(
        FakeSession(),  # type: ignore[arg-type]
        FakeRepository(),  # type: ignore[arg-type]
        FakeConnectorService(),  # type: ignore[arg-type]
        settings(),
    )

    with pytest.raises(PermissionDeniedError):
        await service.authorization_url(
            principal(permissions=frozenset()),
            "01J00000000000000000000007",
        )


@pytest.mark.asyncio
async def test_callback_exchanges_code_and_binds_open_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "app.connectors.feishu.oauth.httpx.AsyncClient",
        lambda **kwargs: FakeAsyncClient(calls, **kwargs),
    )
    session = FakeSession()
    repository = FakeRepository()
    raw_state = "oauth-state-value-with-enough-entropy"
    repository.oauth_state = SimpleNamespace(
        tenant_id=1,
        user_id=7,
        state_hash=hashlib.sha256(raw_state.encode()).hexdigest(),
        code_verifier="verifier-value",
        redirect_uri=settings().feishu_oauth_redirect_uri,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        consumed_at=None,
    )
    service = FeishuOAuthService(
        session,  # type: ignore[arg-type]
        repository,  # type: ignore[arg-type]
        FakeConnectorService(),  # type: ignore[arg-type]
        settings(),
    )

    redirect_url = await service.handle_callback(
        state=raw_state,
        code="authorization-code",
        error=None,
    )

    assert redirect_url == "https://sales.example.com/users?feishu_oauth=success"
    assert repository.user.feishu_open_id == "ou_sales_01"
    assert repository.user.feishu_name == "张三"
    assert repository.user.feishu_bind_status == "bound"
    assert repository.user.phone == "+8613800000000"
    assert repository.oauth_state.consumed_at is not None
    assert calls[0]["json"]["client_id"] == "cli_enterprise"
    assert calls[0]["json"]["code_verifier"] == "verifier-value"
    assert calls[1]["headers"] == {"Authorization": "Bearer u-token"}
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_callback_rejects_consumed_state() -> None:
    repository = FakeRepository()
    raw_state = "already-used-oauth-state"
    repository.oauth_state = SimpleNamespace(
        state_hash=hashlib.sha256(raw_state.encode()).hexdigest(),
        consumed_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    service = FeishuOAuthService(
        FakeSession(),  # type: ignore[arg-type]
        repository,  # type: ignore[arg-type]
        FakeConnectorService(),  # type: ignore[arg-type]
        settings(),
    )

    with pytest.raises(AppError) as error:
        await service.handle_callback(state=raw_state, code="code", error=None)

    assert error.value.code == "FEISHU_OAUTH_STATE_USED"
