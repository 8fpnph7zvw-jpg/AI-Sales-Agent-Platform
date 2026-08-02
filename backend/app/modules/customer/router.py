from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import Principal, require_any_permission
from app.db.session import get_db
from app.modules.customer.repository import CustomerRepository
from app.modules.customer.schemas import (
    CustomerCreate,
    CustomerListResponse,
    CustomerOwnerUpdate,
    CustomerRead,
    CustomerUpdate,
)
from app.modules.customer.service import CustomerService

router = APIRouter(prefix="/customers", tags=["Customers"])


def get_customer_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> CustomerService:
    return CustomerService(session, CustomerRepository(session))


@router.get("", response_model=CustomerListResponse)
async def list_customers(
    service: Annotated[CustomerService, Depends(get_customer_service)],
    principal: Annotated[
        Principal,
        Depends(
            require_any_permission(
                "customer.read_own",
                "customer.read_team",
                "customer.read_all",
            )
        ),
    ],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    search: Annotated[str | None, Query(max_length=160)] = None,
    lifecycle_stage: Annotated[str | None, Query(max_length=32)] = None,
) -> CustomerListResponse:
    customers, total = await service.list_customers(
        principal,
        limit=limit,
        offset=offset,
        search=search,
        lifecycle_stage=lifecycle_stage,
    )
    return CustomerListResponse(
        data=[CustomerRead.model_validate(item) for item in customers],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=CustomerRead, status_code=status.HTTP_201_CREATED)
async def create_customer(
    payload: CustomerCreate,
    service: Annotated[CustomerService, Depends(get_customer_service)],
    principal: Annotated[
        Principal,
        Depends(require_any_permission("customer.create")),
    ],
) -> CustomerRead:
    customer = await service.create_customer(principal, payload)
    return CustomerRead.model_validate(customer)


@router.get("/{customer_id}", response_model=CustomerRead)
async def get_customer(
    customer_id: str,
    service: Annotated[CustomerService, Depends(get_customer_service)],
    principal: Annotated[
        Principal,
        Depends(
            require_any_permission(
                "customer.read_own",
                "customer.read_team",
                "customer.read_all",
            )
        ),
    ],
) -> CustomerRead:
    customer = await service.get_customer(principal, customer_id)
    return CustomerRead.model_validate(customer)


@router.patch("/{customer_id}", response_model=CustomerRead)
async def update_customer(
    customer_id: str,
    payload: CustomerUpdate,
    service: Annotated[CustomerService, Depends(get_customer_service)],
    principal: Annotated[
        Principal,
        Depends(require_any_permission("customer.update_own", "customer.update_all")),
    ],
) -> CustomerRead:
    customer = await service.update_customer(principal, customer_id, payload)
    return CustomerRead.model_validate(customer)


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer(
    customer_id: str,
    service: Annotated[CustomerService, Depends(get_customer_service)],
    principal: Annotated[Principal, Depends(require_any_permission("customer.delete"))],
) -> Response:
    await service.delete_customer(principal, customer_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/{customer_id}/owner", response_model=CustomerRead)
async def assign_customer_owner(
    customer_id: str,
    payload: CustomerOwnerUpdate,
    service: Annotated[CustomerService, Depends(get_customer_service)],
    principal: Annotated[Principal, Depends(require_any_permission("customer.assign"))],
) -> CustomerRead:
    customer = await service.assign_owner(principal, customer_id, payload)
    return CustomerRead.model_validate(customer)
