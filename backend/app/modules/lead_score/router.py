from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import Principal, require_any_permission
from app.core.config import get_settings
from app.core.exceptions import ResourceNotFoundError
from app.db.session import get_db
from app.modules.lead_score.repository import LeadScoreRepository
from app.modules.lead_score.schemas import (
    CustomerCurrentScoreListResponse,
    CustomerScoreListResponse,
    CustomerScoreRead,
    LeadScoreRequest,
    LeadScoreResponse,
    WorkflowScoreRequest,
)
from app.modules.lead_score.service import LeadScoreService
from app.services.dify_scoring_service import DifyScoringService
from app.services.feishu_service import FeishuService
from app.services.lead_scoring_orchestrator import LeadScoringOrchestrator

router = APIRouter(tags=["Lead Score"])


def get_lead_score_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> LeadScoreService:
    return LeadScoreService(session, LeadScoreRepository(session))


@router.post("/lead-score", response_model=LeadScoreResponse)
async def lead_score(
    payload: LeadScoreRequest,
    service: Annotated[LeadScoreService, Depends(get_lead_score_service)],
    principal: Annotated[
        Principal,
        Depends(require_any_permission("customer.score")),
    ],
) -> LeadScoreResponse:
    return await service.score(principal, payload)


@router.get("/lead-scores", response_model=CustomerCurrentScoreListResponse)
async def list_lead_scores(
    service: Annotated[LeadScoreService, Depends(get_lead_score_service)],
    principal: Annotated[
        Principal,
        Depends(require_any_permission("customer.score_read", "customer.score")),
    ],
    customer_id: Annotated[str | None, Query(min_length=26, max_length=26)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CustomerCurrentScoreListResponse:
    return await service.list_current_scores(
        principal,
        customer_id=customer_id,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/lead-scores/{customer_id}/history",
    response_model=CustomerScoreListResponse,
)
async def list_lead_score_history(
    customer_id: Annotated[str, Path(min_length=26, max_length=26)],
    service: Annotated[LeadScoreService, Depends(get_lead_score_service)],
    principal: Annotated[
        Principal,
        Depends(require_any_permission("customer.score_read", "customer.score")),
    ],
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CustomerScoreListResponse:
    return await service.list_scores(
        principal,
        customer_id=customer_id,
        limit=limit,
        offset=offset,
    )


@router.delete(
    "/lead-scores/{customer_id}/history/{score_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_lead_score_history(
    customer_id: Annotated[str, Path(min_length=26, max_length=26)],
    score_id: Annotated[int, Path(ge=1)],
    service: Annotated[LeadScoreService, Depends(get_lead_score_service)],
    principal: Annotated[
        Principal,
        Depends(require_any_permission("customer.score")),
    ],
) -> Response:
    await service.delete_score_history(principal, customer_id, score_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/lead-scores/run", response_model=CustomerScoreRead)
async def run_lead_scoring_workflow(
    payload: WorkflowScoreRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[
        Principal,
        Depends(require_any_permission("customer.score")),
    ],
) -> CustomerScoreRead:
    repository = LeadScoreRepository(session)
    customer = await repository.get_customer(
        principal.tenant_id,
        payload.customer_id,
        owner_user_id=(None if "customer.read_all" in principal.permissions else principal.user_id),
    )
    if customer is None:
        raise ResourceNotFoundError("Customer")
    settings = get_settings()
    score = await LeadScoringOrchestrator(
        session,
        repository,
        DifyScoringService(settings),
        FeishuService(settings),
    ).score_customer(
        customer,
        product_requirement=payload.product_requirement,
        quantity=payload.quantity,
    )
    return CustomerScoreRead(
        id=score.id,
        customer_id=customer.public_id,
        customer_name=customer.name,
        score=score.score,
        level=score.level,
        need_follow=score.need_follow,
        reason=score.reason,
        created_time=score.created_time,
    )
