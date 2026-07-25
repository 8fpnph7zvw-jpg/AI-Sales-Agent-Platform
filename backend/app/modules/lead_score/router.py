from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import Principal, require_any_permission
from app.db.session import get_db
from app.modules.lead_score.repository import LeadScoreRepository
from app.modules.lead_score.schemas import LeadScoreRequest, LeadScoreResponse
from app.modules.lead_score.service import LeadScoreService

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
