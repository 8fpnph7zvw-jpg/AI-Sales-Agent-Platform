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
