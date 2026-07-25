from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.connector.connector import Connector
from app.models.connector.connector_config import ConnectorConfig


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
        return list((await self.session.scalars(statement)).all())

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
        statement = select(ConnectorConfig).where(
            ConnectorConfig.connector_id == connector_id,
            ConnectorConfig.config_key.in_(keys),
        )
        configs = (await self.session.scalars(statement)).all()
        return {config.config_key: config for config in configs}

    def add_config(self, config: ConnectorConfig) -> None:
        self.session.add(config)
