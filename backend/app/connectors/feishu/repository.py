from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth.user import User
from app.models.connector.connector import Connector
from app.models.connector.connector_config import ConnectorConfig


class FeishuConnectorRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_connector(
        self,
        tenant_id: int,
        public_id: str | None = None,
        *,
        for_update: bool = False,
    ) -> Connector | None:
        statement = select(Connector).where(
            Connector.tenant_id == tenant_id,
            Connector.provider == "feishu",
            Connector.deleted_at.is_(None),
        )
        if public_id is not None:
            statement = statement.where(Connector.public_id == public_id)
        statement = statement.order_by(Connector.id.desc()).limit(1)
        if for_update:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def get_configs(self, connector_id: int) -> dict[str, ConnectorConfig]:
        configs = (
            await self.session.scalars(
                select(ConnectorConfig).where(
                    ConnectorConfig.connector_id == connector_id,
                    ConnectorConfig.config_key.in_(("app_id", "app_secret")),
                )
            )
        ).all()
        return {config.config_key: config for config in configs}

    async def get_user(self, tenant_id: int, user_id: int) -> User | None:
        return await self.session.scalar(
            select(User).where(
                User.tenant_id == tenant_id,
                User.id == user_id,
                User.deleted_at.is_(None),
            )
        )
