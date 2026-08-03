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
    QuotationStatus,
    QuotationStatusResponse,
    QuotationStatusUpdate,
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
    status_filter: Annotated[QuotationStatus | None, Query(alias="status")] = None,
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


@router.patch(
    "/quotations/{quotation_id}/status",
    response_model=QuotationStatusResponse,
)
async def update_quotation_status(
    quotation_id: str,
    payload: QuotationStatusUpdate,
    service: Annotated[QuotationService, Depends(get_quotation_service)],
    principal: Annotated[
        Principal,
        Depends(require_any_permission("quotation.update_own")),
    ],
) -> QuotationStatusResponse:
    return await service.update_status(principal, quotation_id, payload)


@router.delete(
    "/quotations/{quotation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_quotation(
    quotation_id: str,
    service: Annotated[QuotationService, Depends(get_quotation_service)],
    principal: Annotated[
        Principal,
        Depends(require_any_permission("quotation.update_own")),
    ],
) -> None:
    await service.delete(principal, quotation_id)
