from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow.workflow import Workflow


class WorkflowRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(
        self,
        tenant_id: int,
        *,
        limit: int,
        offset: int,
        status: str | None,
    ) -> tuple[list[Workflow], int]:
        filters = [
            Workflow.tenant_id == tenant_id,
            Workflow.deleted_at.is_(None),
        ]
        if status:
            filters.append(Workflow.status == status)
        rows = list(
            (
                await self.session.scalars(
                    select(Workflow)
                    .where(*filters)
                    .order_by(Workflow.updated_at.desc(), Workflow.id.desc())
                    .limit(limit)
                    .offset(offset)
                )
            ).all()
        )
        total = int(
            (await self.session.scalar(select(func.count(Workflow.id)).where(*filters))) or 0
        )
        return rows, total
