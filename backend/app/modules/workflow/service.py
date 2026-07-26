from __future__ import annotations

from app.api.dependencies.auth import Principal
from app.modules.workflow.repository import WorkflowRepository
from app.modules.workflow.schemas import WorkflowListResponse, WorkflowRead


class WorkflowService:
    def __init__(self, repository: WorkflowRepository) -> None:
        self.repository = repository

    async def list(
        self,
        principal: Principal,
        *,
        limit: int,
        offset: int,
        status: str | None,
    ) -> WorkflowListResponse:
        workflows, total = await self.repository.list(
            principal.tenant_id,
            limit=limit,
            offset=offset,
            status=status,
        )
        return WorkflowListResponse(
            data=[
                WorkflowRead(
                    id=workflow.public_id,
                    name=workflow.name,
                    description=(workflow.definition or {}).get("description"),
                    status=workflow.status,
                    version=workflow.version,
                    trigger_type=workflow.trigger_type,
                    updated_at=workflow.updated_at,
                )
                for workflow in workflows
            ],
            total=total,
            limit=limit,
            offset=offset,
        )
