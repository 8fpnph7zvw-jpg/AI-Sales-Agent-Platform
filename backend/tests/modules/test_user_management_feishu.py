from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from app.api.dependencies.auth import Principal
from app.core.exceptions import PermissionDeniedError
from app.modules.user_management.service import UserManagementService


class FakeRepository:
    def __init__(self, user: Any) -> None:
        self.user = user

    async def get(self, tenant_id: int, public_id: str, **_kwargs: Any) -> Any:
        assert tenant_id == 1
        return self.user if public_id == self.user.public_id else None


def principal(*, user_public_id: str, permissions: frozenset[str]) -> Principal:
    return Principal(
        user_id=1,
        user_public_id=user_public_id,
        tenant_id=1,
        tenant_public_id="01J00000000000000000000000",
        permissions=permissions,
    )


@pytest.mark.asyncio
async def test_admin_can_read_bound_user_feishu_status() -> None:
    bind_time = datetime.now(UTC)
    user = SimpleNamespace(
        public_id="01J00000000000000000000007",
        feishu_bind_status="bound",
        feishu_open_id="ou_sales",
        feishu_name="张三",
        feishu_bind_time=bind_time,
    )
    service = UserManagementService(
        SimpleNamespace(),  # type: ignore[arg-type]
        FakeRepository(user),  # type: ignore[arg-type]
        SimpleNamespace(),  # type: ignore[arg-type]
    )

    result = await service.feishu_status(
        principal(
            user_public_id="01J00000000000000000000001",
            permissions=frozenset({"user.read"}),
        ),
        user.public_id,
    )

    assert result.user_id == user.public_id
    assert result.bound is True
    assert result.feishu_name == "张三"
    assert result.bind_time == bind_time


@pytest.mark.asyncio
async def test_user_without_permission_can_only_read_own_feishu_status() -> None:
    user = SimpleNamespace(
        public_id="01J00000000000000000000007",
        feishu_bind_status="unbound",
        feishu_open_id=None,
        feishu_name=None,
        feishu_bind_time=None,
    )
    service = UserManagementService(
        SimpleNamespace(),  # type: ignore[arg-type]
        FakeRepository(user),  # type: ignore[arg-type]
        SimpleNamespace(),  # type: ignore[arg-type]
    )

    with pytest.raises(PermissionDeniedError):
        await service.feishu_status(
            principal(
                user_public_id="01J00000000000000000000001",
                permissions=frozenset(),
            ),
            user.public_id,
        )

    own = await service.feishu_status(
        principal(user_public_id=user.public_id, permissions=frozenset()),
        user.public_id,
    )
    assert own.bound is False
