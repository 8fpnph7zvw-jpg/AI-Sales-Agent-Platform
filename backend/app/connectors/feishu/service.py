from __future__ import annotations

import logging
from collections import OrderedDict
from datetime import UTC, datetime
from hashlib import sha256

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import Principal
from app.core.config import Settings
from app.core.encryption import ConfigCipher
from app.core.exceptions import ConflictError, ResourceNotFoundError, ServiceConfigurationError
from app.integrations.feishu.client import FeishuClient
from app.integrations.feishu.schemas import FeishuSendResult
from app.services.feishu_service import FeishuService

from .repository import FeishuConnectorRepository

logger = logging.getLogger(__name__)

FEISHU_APP_ID_KEY = "app_id"
FEISHU_APP_SECRET_KEY = "app_secret"
FEISHU_CONFIG_KEYS = frozenset({FEISHU_APP_ID_KEY, FEISHU_APP_SECRET_KEY})
FEISHU_SECRET_KEYS = frozenset({FEISHU_APP_SECRET_KEY})
TEST_MESSAGE = "AI Sales Agent 飞书通知测试成功"
SERVICE_CACHE_SIZE = 256
_service_cache: OrderedDict[tuple[int, int, str], FeishuService] = OrderedDict()


class FeishuConnectorService:
    """Resolve one tenant's enterprise Feishu App and dispatch its messages."""

    def __init__(
        self,
        session: AsyncSession,
        repository: FeishuConnectorRepository,
        cipher: ConfigCipher,
        settings: Settings,
    ) -> None:
        self.session = session
        self.repository = repository
        self.cipher = cipher
        self.settings = settings

    async def config_status(self, principal: Principal, connector_id: str) -> dict[str, object]:
        connector = await self.repository.get_connector(principal.tenant_id, connector_id)
        if connector is None:
            raise ResourceNotFoundError("Feishu Connector")
        configs = await self.repository.get_configs(connector.id)
        return {
            "connector_id": connector.public_id,
            "configured_keys": sorted(configs),
            "status": connector.status,
            "health_status": connector.health_status,
            "last_health_check_at": connector.last_health_check_at,
        }

    async def test_notification(self, principal: Principal) -> FeishuSendResult:
        user = await self.repository.get_user(principal.tenant_id, principal.user_id)
        if user is None:
            raise ResourceNotFoundError("Current user")
        if user.feishu_bind_status != "bound" or not user.feishu_open_id:
            logger.info(
                "feishu_not_bound tenant_id=%s user_id=%s purpose=connector_test",
                principal.tenant_id,
                principal.user_id,
            )
            raise ConflictError("FEISHU_NOT_BOUND", "请先绑定飞书账号")

        connector = await self.repository.get_connector(
            principal.tenant_id,
            for_update=True,
        )
        if connector is None:
            raise ResourceNotFoundError("Feishu Connector")
        try:
            service = await self._service(connector)
            await service.test_connection()
            result = await service.send_message(
                user.feishu_open_id,
                TEST_MESSAGE,
                user_id=str(user.id),
            )
        except Exception as exc:
            connector.status = "error"
            connector.health_status = "unhealthy"
            connector.health_detail = {"message": str(exc)[:500]}
            connector.last_health_check_at = datetime.now(UTC)
            await self.session.commit()
            raise

        now = datetime.now(UTC)
        connector.status = "active"
        connector.health_status = "healthy"
        connector.health_detail = {"message": "Feishu token and message API are available."}
        connector.last_health_check_at = now
        connector.last_connected_at = now
        connector.last_disconnect_reason = None
        await self.session.commit()
        return result

    async def send_message(
        self,
        tenant_id: int,
        receive_id: str,
        content: str,
        *,
        customer_id: str | None = None,
        user_id: str | None = None,
    ) -> FeishuSendResult:
        connector = await self.repository.get_connector(tenant_id)
        if connector is None:
            raise ServiceConfigurationError("Feishu Connector is not configured.")
        service = await self._service(connector)
        return await service.send_message(
            receive_id,
            content,
            customer_id=customer_id,
            user_id=user_id,
        )

    async def _service(self, connector) -> FeishuService:
        configs = await self.repository.get_configs(connector.id)
        missing = FEISHU_CONFIG_KEYS - configs.keys()
        if missing:
            raise ServiceConfigurationError(
                f"Feishu Connector is missing configuration: {', '.join(sorted(missing))}."
            )
        values: dict[str, str] = {}
        for key in FEISHU_CONFIG_KEYS:
            config = configs[key]
            if config.value_encrypted is None:
                raise ServiceConfigurationError(f"Feishu Connector configuration {key} is empty.")
            value = self.cipher.decrypt(
                config.value_encrypted,
                associated_data=f"{connector.tenant_id}:{connector.id}:{key}",
            )
            values[key] = str(value).strip()
        if not all(values.values()):
            raise ServiceConfigurationError("Feishu App ID and App Secret are required.")
        credential_fingerprint = sha256(
            (
                f"{values[FEISHU_APP_ID_KEY]}\0{values[FEISHU_APP_SECRET_KEY]}\0"
                f"{self.settings.feishu_api_base_url}\0{self.settings.feishu_timeout_seconds}"
            ).encode()
        ).hexdigest()
        cache_key = (connector.tenant_id, connector.id, credential_fingerprint)
        if cached := _service_cache.get(cache_key):
            _service_cache.move_to_end(cache_key)
            return cached
        service = FeishuService(
            FeishuClient(
                self.settings,
                app_id=values[FEISHU_APP_ID_KEY],
                app_secret=values[FEISHU_APP_SECRET_KEY],
                enabled=True,
            )
        )
        _service_cache[cache_key] = service
        _service_cache.move_to_end(cache_key)
        while len(_service_cache) > SERVICE_CACHE_SIZE:
            _service_cache.popitem(last=False)
        return service
