from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth.role import Role
from app.models.auth.user import User
from app.models.auth.user_role import UserRole
from app.models.connector.connector import Connector
from app.models.connector.connector_config import DEFAULT_OWNER_CONFIG_KEY, ConnectorConfig


class ConnectorRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, tenant_id: int) -> list[Connector]:
        statement = (
            select(Connector)
            .where(
                Connector.tenant_id == tenant_id,
                Connector.deleted_at.is_(None),
            )
            .order_by(Connector.created_at.desc(), Connector.id.desc())
        )
        connectors = list((await self.session.scalars(statement)).all())
        whatsapp = [item for item in connectors if item.provider == "whatsapp"]
        if len(whatsapp) <= 1:
            return connectors
        keeper = max(
            whatsapp,
            key=lambda item: (
                item.external_account_id != "demo-template",
                item.status == "active",
                item.last_connected_at is not None,
                item.last_connected_at,
                item.id,
            ),
        )
        return [item for item in connectors if item.provider != "whatsapp" or item.id == keeper.id]

    async def get_for_update(
        self,
        tenant_id: int,
        public_id: str,
    ) -> Connector | None:
        statement = (
            select(Connector)
            .where(
                Connector.tenant_id == tenant_id,
                Connector.public_id == public_id,
                Connector.deleted_at.is_(None),
            )
            .with_for_update()
        )
        return await self.session.scalar(statement)

    async def get_configs(
        self,
        connector_id: int,
        keys: set[str],
    ) -> dict[str, ConnectorConfig]:
        statement = select(ConnectorConfig).where(ConnectorConfig.connector_id == connector_id)
        if keys:
            statement = statement.where(ConnectorConfig.config_key.in_(keys))
        configs = (await self.session.scalars(statement)).all()
        return {config.config_key: config for config in configs}

    def add_config(self, config: ConnectorConfig) -> None:
        self.session.add(config)

    async def get_default_owner_config(self, connector_id: int) -> ConnectorConfig | None:
        return await self.session.scalar(
            select(ConnectorConfig).where(
                ConnectorConfig.connector_id == connector_id,
                ConnectorConfig.config_key == DEFAULT_OWNER_CONFIG_KEY,
            )
        )

    async def get_sales_user(self, tenant_id: int, public_id: str) -> User | None:
        return await self.session.scalar(
            select(User)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(
                User.tenant_id == tenant_id,
                User.public_id == public_id,
                User.status == "active",
                User.deleted_at.is_(None),
                Role.tenant_id == tenant_id,
                Role.code == "sales",
            )
            .limit(1)
        )
