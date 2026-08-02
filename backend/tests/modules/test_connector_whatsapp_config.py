from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.api.dependencies.auth import Principal
from app.models.connector.connector_config import ConnectorConfig
from app.modules.connector.schemas import ConnectorConfigRequest
from app.modules.connector.service import ConnectorService


class FakeCipher:
    key_version = "test-v1"

    def encrypt(self, value: Any, *, associated_data: str) -> bytes:
        assert value
        assert associated_data.startswith("1:10:")
        return b"encrypted"

    def decrypt(self, encrypted: bytes, *, associated_data: str) -> Any:
        raise AssertionError("No existing configuration should be decrypted in this test.")


class FakeRepository:
    def __init__(self, connector: SimpleNamespace) -> None:
        self.connector = connector
        self.configs: list[ConnectorConfig] = []

    async def get_for_update(
        self,
        tenant_id: int,
        public_id: str,
    ) -> SimpleNamespace:
        assert tenant_id == 1
        assert public_id == self.connector.public_id
        return self.connector

    async def get_configs(
        self,
        connector_id: int,
        keys: set[str],
    ) -> dict[str, ConnectorConfig]:
        assert connector_id == 10
        return {}

    def add_config(self, config: ConnectorConfig) -> None:
        self.configs.append(config)

    async def get_default_owner_config(self, connector_id: int) -> ConnectorConfig | None:
        assert connector_id == 10
        return next(
            (config for config in self.configs if config.config_key == "default_owner_user_id"),
            None,
        )

    async def get_sales_user(
        self, tenant_id: int, public_id: str
    ) -> SimpleNamespace | None:
        assert tenant_id == 1
        if public_id == "01ARZ3NDEKTSV4RRFFQ69G5FAX":
            return SimpleNamespace(id=30, public_id=public_id)
        return None


class FakeSession:
    committed = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        raise AssertionError("Rollback is not expected.")


@pytest.mark.asyncio
async def test_whatsapp_cloud_config_is_stored_and_phone_becomes_external_id() -> None:
    connector = SimpleNamespace(
        id=10,
        public_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
        provider="whatsapp",
        external_account_id="demo-template",
        status="disabled",
        health_status=None,
        health_detail=None,
        last_health_check_at=None,
    )
    repository = FakeRepository(connector)
    session = FakeSession()
    service = ConnectorService(session, repository, FakeCipher())
    principal = Principal(
        user_id=20,
        user_public_id="user-public-id",
        tenant_id=1,
        tenant_public_id="tenant-public-id",
        permissions=frozenset({"connector.secret_manage"}),
    )
    payload = ConnectorConfigRequest.model_validate(
        {
            "connector_id": connector.public_id,
            "values": [
                {
                    "key": "phone_number_id",
                    "value": "123456789",
                    "is_secret": False,
                },
                {"key": "access_token", "value": "token", "is_secret": False},
                {"key": "verify_token", "value": "verify", "is_secret": False},
                {"key": "app_secret", "value": "secret", "is_secret": False},
            ],
        }
    )

    response = await service.configure(principal, payload)

    stored = {config.config_key: config for config in repository.configs}
    assert stored["phone_number_id"].value_encrypted == b"encrypted"
    assert stored["phone_number_id"].is_secret is False
    assert stored["access_token"].is_secret is True
    assert stored["verify_token"].is_secret is True
    assert stored["app_secret"].is_secret is True
    assert connector.external_account_id == "123456789"
    assert connector.status == "draft"
    assert session.committed is True
    assert "123456789" not in response.model_dump_json()


@pytest.mark.asyncio
async def test_whatsapp_web_config_saves_adapter_and_session_id() -> None:
    connector = SimpleNamespace(
        id=10,
        public_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
        provider="whatsapp",
        external_account_id="demo-template",
        session_id=None,
        status="disabled",
        health_status=None,
        health_detail=None,
        last_health_check_at=None,
    )
    repository = FakeRepository(connector)
    session = FakeSession()
    service = ConnectorService(session, repository, FakeCipher())
    principal = Principal(
        user_id=20,
        user_public_id="user-public-id",
        tenant_id=1,
        tenant_public_id="tenant-public-id",
        permissions=frozenset({"connector.secret_manage"}),
    )
    payload = ConnectorConfigRequest.model_validate(
        {
            "connector_id": connector.public_id,
            "values": [
                {"key": "adapter", "value": "webjs_gateway", "is_secret": False},
                {"key": "session_id", "value": "sales-web-01", "is_secret": False},
            ],
        }
    )

    await service.configure(principal, payload)

    assert {config.config_key for config in repository.configs} == {
        "adapter",
        "session_id",
    }
    assert connector.session_id == "sales-web-01"
    assert connector.external_account_id == "sales-web-01"
    assert connector.status == "draft"


@pytest.mark.asyncio
async def test_whatsapp_default_owner_maps_public_id_to_internal_sales_id() -> None:
    connector = SimpleNamespace(
        id=10,
        public_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
        provider="whatsapp",
        external_account_id="configured-account",
        session_id=None,
        status="active",
        health_status="healthy",
        health_detail=None,
        last_health_check_at=None,
    )
    repository = FakeRepository(connector)
    session = FakeSession()
    service = ConnectorService(session, repository, FakeCipher())
    principal = Principal(
        user_id=20,
        user_public_id="admin-public-id",
        tenant_id=1,
        tenant_public_id="tenant-public-id",
        permissions=frozenset({"connector.secret_manage"}),
    )
    payload = ConnectorConfigRequest.model_validate(
        {
            "connector_id": connector.public_id,
            "values": [],
            "default_owner_id": "01ARZ3NDEKTSV4RRFFQ69G5FAX",
        }
    )

    response = await service.configure(principal, payload)

    owner_config = repository.configs[0]
    assert owner_config.config_key == "default_owner_user_id"
    assert owner_config.default_owner_user_id == 30
    assert owner_config.is_secret is False
    assert response.default_owner_id == "01ARZ3NDEKTSV4RRFFQ69G5FAX"
    assert connector.status == "active"
    assert session.committed is True
