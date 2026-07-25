from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import Principal
from app.core.encryption import ConfigCipher
from app.core.exceptions import ConflictError, ResourceNotFoundError
from app.models.connector.connector import Connector
from app.models.connector.connector_config import ConnectorConfig
from app.modules.connector.repository import ConnectorRepository
from app.modules.connector.schemas import ConnectorConfigRequest, ConnectorConfigResponse


class ConnectorService:
    def __init__(
        self,
        session: AsyncSession,
        repository: ConnectorRepository,
        cipher: ConfigCipher,
    ) -> None:
        self.session = session
        self.repository = repository
        self.cipher = cipher

    async def list(self, principal: Principal) -> list[Connector]:
        return await self.repository.list(principal.tenant_id)

    async def configure(
        self,
        principal: Principal,
        payload: ConnectorConfigRequest,
    ) -> ConnectorConfigResponse:
        connector = await self.repository.get_for_update(
            principal.tenant_id,
            payload.connector_id,
        )
        if connector is None:
            raise ResourceNotFoundError("Connector")

        keys = [item.key for item in payload.values]
        if len(keys) != len(set(keys)):
            raise ConflictError(
                "DUPLICATE_CONFIG_KEY",
                "Connector configuration keys must be unique in one request.",
            )
        existing = await self.repository.get_configs(connector.id, set(keys))
        for item in payload.values:
            config = existing.get(item.key)
            if config is None:
                config = ConnectorConfig(
                    tenant_id=principal.tenant_id,
                    connector_id=connector.id,
                    config_key=item.key,
                )
                self.repository.add_config(config)
            associated_data = f"{principal.tenant_id}:{connector.id}:{item.key}"
            config.value_type = item.value_type
            config.value_encrypted = self.cipher.encrypt(
                item.value,
                associated_data=associated_data,
            )
            config.secret_ref = None
            config.key_version = self.cipher.key_version
            config.is_secret = item.is_secret
            config.updated_by = principal.user_id

        await self.session.commit()
        return ConnectorConfigResponse(
            connector_id=connector.public_id,
            configured_keys=sorted(keys),
            key_version=self.cipher.key_version,
        )
