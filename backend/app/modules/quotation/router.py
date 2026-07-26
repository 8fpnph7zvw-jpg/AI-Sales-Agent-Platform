from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import Principal, require_any_permission
from app.db.session import get_db
from app.modules.quotation.repository import QuotationRepository
from app.modules.quotation.schemas import (
    ProductListResponse,
    QuotationCreate,
    QuotationListResponse,
    QuotationResponse,
)
from app.modules.quotation.service import QuotationService

router = APIRouter(tags=["Quotation"])


def get_quotation_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> QuotationService:
    return QuotationService(session, QuotationRepository(session))


@router.get("/quotations", response_model=QuotationListResponse)
async def list_quotations(
    service: Annotated[QuotationService, Depends(get_quotation_service)],
    principal: Annotated[
        Principal,
        Depends(require_any_permission("quotation.read_own", "quotation.read_all")),
    ],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    status_filter: Annotated[str | None, Query(alias="status", max_length=24)] = None,
) -> QuotationListResponse:
    return await service.list_quotations(
        principal,
        limit=limit,
        offset=offset,
        status=status_filter,
    )


@router.get("/products", response_model=ProductListResponse)
async def list_products(
    service: Annotated[QuotationService, Depends(get_quotation_service)],
    principal: Annotated[
        Principal,
        Depends(require_any_permission("product.read", "quotation.create")),
    ],
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ProductListResponse:
    return await service.list_products(principal, limit=limit, offset=offset)


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
