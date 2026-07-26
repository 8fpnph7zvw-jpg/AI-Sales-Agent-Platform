from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import Principal, require_any_permission
from app.db.session import get_db
from app.modules.workflow.repository import WorkflowRepository
from app.modules.workflow.schemas import WorkflowListResponse
from app.modules.workflow.service import WorkflowService

router = APIRouter(prefix="/workflows", tags=["Workflows"])


def get_workflow_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> WorkflowService:
    return WorkflowService(WorkflowRepository(session))


@router.get("", response_model=WorkflowListResponse)
async def list_workflows(
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
    principal: Annotated[
        Principal,
        Depends(require_any_permission("workflow.read", "workflow.manage")),
    ],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    status_filter: Annotated[str | None, Query(alias="status", max_length=24)] = None,
) -> WorkflowListResponse:
    return await service.list(
        principal,
        limit=limit,
        offset=offset,
        status=status_filter,
    )
