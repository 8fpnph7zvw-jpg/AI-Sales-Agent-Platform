from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.core.config import Settings
from app.core.security import SecurityManager
from app.modules.auth.schemas import LoginRequest, RefreshTokenRequest
from app.modules.auth.service import AuthService


@pytest.mark.asyncio
async def test_login_creates_and_refresh_rotates_persistent_session() -> None:
    settings = Settings(
        _env_file=None,
        jwt_secret="a-secure-test-secret-with-more-than-32-characters",
        access_token_expire_minutes=24 * 60,
        refresh_token_expire_days=30,
    )
    security = SecurityManager(settings)
    user = SimpleNamespace(
        id=11,
        public_id="01USERPUBLIC00000000000000",
        password_hash=security.hash_password("correct horse battery staple"),
        status="active",
        display_name="Sales Admin",
        email="admin@example.com",
        last_login_at=None,
    )
    tenant = SimpleNamespace(
        id=7,
        public_id="01TENANTPUBLIC000000000000",
        status="active",
    )
    repository = SimpleNamespace(
        get_login_identity=AsyncMock(return_value=(user, tenant)),
        get_permission_codes=AsyncMock(return_value={"connector.manage"}),
        add_auth_session=Mock(),
        get_refresh_session=AsyncMock(),
    )
    session = SimpleNamespace(commit=AsyncMock())
    service = AuthService(
        session=session,
        repository=repository,
        security=security,
    )

    login = await service.login(
        LoginRequest(
            tenant_slug="acme",
            email="admin@example.com",
            password="correct horse battery staple",
        )
    )
    auth_session = repository.add_auth_session.call_args.args[0]
    original_hash = auth_session.refresh_token_hash
    repository.get_refresh_session.return_value = (auth_session, user, tenant)

    refreshed = await service.refresh(
        RefreshTokenRequest(refresh_token=login.refresh_token)
    )

    assert login.expires_in == 24 * 60 * 60
    assert login.refresh_expires_in == 30 * 24 * 60 * 60
    assert security.hash_refresh_token(login.refresh_token) == original_hash
    assert refreshed.access_token != login.access_token
    assert refreshed.refresh_token != login.refresh_token
    assert auth_session.refresh_token_hash == security.hash_refresh_token(
        refreshed.refresh_token
    )
    assert auth_session.last_used_at is not None
    assert session.commit.await_count == 2
