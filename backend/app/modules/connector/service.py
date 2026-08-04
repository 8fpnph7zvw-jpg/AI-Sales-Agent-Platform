from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import Principal
from app.connectors.feishu.service import FEISHU_CONFIG_KEYS, FEISHU_SECRET_KEYS
from app.connectors.whatsapp.client import (
    SECRET_CONFIG_KEYS,
    SUPPORTED_CONFIG_KEYS,
    WhatsAppConnector,
)
from app.core.encryption import ConfigCipher
from app.core.exceptions import ConflictError, ResourceNotFoundError
from app.models.connector.connector import Connector
from app.models.connector.connector_config import DEFAULT_OWNER_CONFIG_KEY, ConnectorConfig
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
        if connector.provider == "whatsapp" and payload.values:
            if unsupported := set(keys) - SUPPORTED_CONFIG_KEYS:
                raise ConflictError(
                    "WHATSAPP_CONFIG_KEY_UNSUPPORTED",
                    f"Unsupported WhatsApp configuration key: {sorted(unsupported)[0]}",
                )
            if errors := WhatsAppConnector.validate_config(effective_values):
                raise ConflictError(
                    "WHATSAPP_CONFIG_INCOMPLETE",
                    "; ".join(errors),
                )
        if connector.provider == "feishu" and payload.values:
            if unsupported := set(keys) - FEISHU_CONFIG_KEYS:
                raise ConflictError(
                    "FEISHU_CONFIG_KEY_UNSUPPORTED",
                    f"Unsupported Feishu configuration key: {sorted(unsupported)[0]}",
                )
            missing = [key for key in FEISHU_CONFIG_KEYS if not effective_values.get(key)]
            if missing:
                raise ConflictError(
                    "FEISHU_CONFIG_INCOMPLETE",
                    f"Missing Feishu configuration: {', '.join(sorted(missing))}",
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
                else (
                    item.key in FEISHU_SECRET_KEYS
                    if connector.provider == "feishu"
                    else item.is_secret
                )
            )
            config.updated_by = principal.user_id

        default_owner_id: str | None = None
        if "default_owner_id" in payload.model_fields_set:
            owner_config = await self.repository.get_default_owner_config(connector.id)
            if owner_config is None:
                owner_config = ConnectorConfig(
                    tenant_id=principal.tenant_id,
                    connector_id=connector.id,
                    config_key=DEFAULT_OWNER_CONFIG_KEY,
                    value_type="user_reference",
                    is_secret=False,
                )
                self.repository.add_config(owner_config)
            owner_config.updated_by = principal.user_id
            if payload.default_owner_id is None:
                owner_config.default_owner_user_id = None
            else:
                owner = await self.repository.get_sales_user(
                    principal.tenant_id,
                    payload.default_owner_id,
                )
                if owner is None:
                    raise ResourceNotFoundError("Active sales user")
                owner_config.default_owner_user_id = owner.id
                default_owner_id = owner.public_id

        if connector.provider == "whatsapp" and payload.values:
            external_account_id = effective_values.get("phone_number_id")
            if str(effective_values.get("adapter") or "cloud_api") == "webjs_gateway":
                external_account_id = effective_values.get("session_id")
                connector.session_id = str(external_account_id).strip()
            else:
                connector.session_id = None
            connector.external_account_id = str(external_account_id).strip()
            connector.status = "draft"
            connector.health_status = None
            connector.health_detail = {
                "message": "Configuration saved; connection test required."
            }
            connector.last_health_check_at = None
        if connector.provider == "feishu" and payload.values:
            connector.external_account_id = str(effective_values["app_id"]).strip()
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
            default_owner_id=default_owner_id,
        )
