from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.api.dependencies.auth import Principal
from app.connectors.feishu.service import TEST_MESSAGE, FeishuConnectorService
from app.core.config import Settings
from app.core.exceptions import ConflictError
from app.integrations.feishu.schemas import FeishuSendResult


class FakeSession:
    def __init__(self) -> None:
        self.commit_count = 0

    async def commit(self) -> None:
        self.commit_count += 1


class FakeRepository:
    def __init__(self, user: Any) -> None:
        self.user = user
        self.connector = SimpleNamespace(
            id=10,
            public_id="01J00000000000000000000001",
            tenant_id=1,
            status="draft",
            health_status=None,
            health_detail=None,
            last_health_check_at=None,
            last_connected_at=None,
            last_disconnect_reason=None,
        )

    async def get_user(self, tenant_id: int, user_id: int) -> Any:
        assert (tenant_id, user_id) == (1, 7)
        return self.user

    async def get_connector(self, tenant_id: int, *_args: Any, **_kwargs: Any) -> Any:
        assert tenant_id == 1
        return self.connector


class FakeFeishu:
    def __init__(self) -> None:
        self.tested = False
        self.calls: list[tuple[str, str, str | None]] = []

    async def test_connection(self) -> bool:
        self.tested = True
        return True

    async def send_message(
        self,
        receive_id: str,
        content: str,
        *,
        user_id: str | None = None,
    ) -> FeishuSendResult:
        self.calls.append((receive_id, content, user_id))
        return FeishuSendResult(message_id="om_test")


def principal() -> Principal:
    return Principal(
        user_id=7,
        user_public_id="01J00000000000000000000007",
        tenant_id=1,
        tenant_public_id="01J00000000000000000000008",
        permissions=frozenset({"connector.manage"}),
    )


@pytest.mark.asyncio
async def test_bound_admin_receives_connector_test(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession()
    repository = FakeRepository(
        SimpleNamespace(
            id=7,
            feishu_bind_status="bound",
            feishu_open_id="ou_admin",
        )
    )
    service = FeishuConnectorService(
        session,  # type: ignore[arg-type]
        repository,  # type: ignore[arg-type]
        SimpleNamespace(),  # type: ignore[arg-type]
        Settings(_env_file=None),
    )
    feishu = FakeFeishu()

    async def fake_service(_connector: Any) -> FakeFeishu:
        return feishu

    monkeypatch.setattr(service, "_service", fake_service)

    result = await service.test_notification(principal())

    assert result.message_id == "om_test"
    assert feishu.tested is True
    assert feishu.calls == [("ou_admin", TEST_MESSAGE, "7")]
    assert repository.connector.status == "active"
    assert repository.connector.health_status == "healthy"
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_unbound_admin_gets_binding_prompt() -> None:
    session = FakeSession()
    repository = FakeRepository(
        SimpleNamespace(id=7, feishu_bind_status="unbound", feishu_open_id=None)
    )
    service = FeishuConnectorService(
        session,  # type: ignore[arg-type]
        repository,  # type: ignore[arg-type]
        SimpleNamespace(),  # type: ignore[arg-type]
        Settings(_env_file=None),
    )

    with pytest.raises(ConflictError) as error:
        await service.test_notification(principal())

    assert error.value.code == "FEISHU_NOT_BOUND"
    assert error.value.message == "请先绑定飞书账号"
    assert session.commit_count == 0
