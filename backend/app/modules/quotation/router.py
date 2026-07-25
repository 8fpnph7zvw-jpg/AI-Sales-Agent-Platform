from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import Principal, require_any_permission
from app.db.session import get_db
from app.modules.quotation.repository import QuotationRepository
from app.modules.quotation.schemas import QuotationCreate, QuotationResponse
from app.modules.quotation.service import QuotationService

router = APIRouter(tags=["Quotation"])


def get_quotation_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> QuotationService:
    return QuotationService(session, QuotationRepository(session))


@router.post(
    "/quotation",
    response_model=QuotationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_quotation(
    payload: QuotationCreate,
    service: Annotated[QuotationService, Depends(get_quotation_service)],
    principal: Annotated[
        Principal,
        Depends(require_any_permission("quotation.create")),
    ],
) -> QuotationResponse:
    return await service.create(principal, payload)
