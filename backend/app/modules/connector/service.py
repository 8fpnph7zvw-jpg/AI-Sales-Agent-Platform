from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import Principal
from app.connectors.whatsapp.client import (
    SECRET_CONFIG_KEYS,
    WhatsAppConnector,
)
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
        all_existing = await self.repository.get_configs(connector.id, set())
        effective_values = {
            key: self.cipher.decrypt(
                config.value_encrypted,
                associated_data=f"{principal.tenant_id}:{connector.id}:{key}",
            )
            for key, config in all_existing.items()
            if config.value_encrypted is not None
        }
        effective_values.update({item.key: item.value for item in payload.values})
        if connector.provider == "whatsapp":
            allowed_keys = {
                "phone_number_id",
                "business_account_id",
                "access_token",
                "verify_token",
                "app_secret",
            }
            if unsupported := set(keys) - allowed_keys:
                raise ConflictError(
                    "WHATSAPP_CONFIG_KEY_UNSUPPORTED",
                    f"Unsupported WhatsApp configuration key: {sorted(unsupported)[0]}",
                )
            if errors := WhatsAppConnector.validate_config(effective_values):
                raise ConflictError(
                    "WHATSAPP_CONFIG_INCOMPLETE",
                    "; ".join(errors),
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
            config.is_secret = (
                True
                if connector.provider == "whatsapp" and item.key in SECRET_CONFIG_KEYS
                else item.is_secret
            )
            config.updated_by = principal.user_id

        if connector.provider == "whatsapp":
            connector.external_account_id = str(effective_values["phone_number_id"]).strip()
            connector.status = "draft"
            connector.health_status = None
            connector.health_detail = {
                "message": "Configuration saved; connection test required."
            }
            connector.last_health_check_at = None
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError(
                "CONNECTOR_ACCOUNT_ALREADY_CONFIGURED",
                "This provider account is already configured for the tenant.",
            ) from exc
        return ConnectorConfigResponse(
            connector_id=connector.public_id,
            configured_keys=sorted(keys),
            key_version=self.cipher.key_version,
        )
