from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import Principal
from app.core.exceptions import ConflictError, ResourceNotFoundError
from app.db.base import new_ulid
from app.models.quotation.product import Product
from app.models.quotation.quotation import Quotation
from app.models.quotation.quotation_item import QuotationItem
from app.modules.quotation.repository import QuotationRepository
from app.modules.quotation.schemas import (
    ProductListResponse,
    ProductRead,
    QuotationCreate,
    QuotationItemCreate,
    QuotationItemResponse,
    QuotationListItem,
    QuotationListResponse,
    QuotationResponse,
    QuotationStatusResponse,
    QuotationStatusUpdate,
)
from app.services.customer_category_service import CustomerCategoryService

MONEY = Decimal("0.0001")
HUNDRED = Decimal("100")


class QuotationService:
    def __init__(
        self,
        session: AsyncSession,
        repository: QuotationRepository,
    ) -> None:
        self.session = session
        self.repository = repository
        self.customer_category = CustomerCategoryService()

    async def list_quotations(
        self,
        principal: Principal,
        *,
        limit: int,
        offset: int,
        status: str | None,
    ) -> QuotationListResponse:
        created_by = None if "quotation.read_all" in principal.permissions else principal.user_id
        rows, total = await self.repository.list_quotations(
            principal.tenant_id,
            limit=limit,
            offset=offset,
            status=status,
            created_by=created_by,
        )
        return QuotationListResponse(
            data=[
                QuotationListItem(
                    id=quotation.public_id,
                    quotation_no=quotation.quotation_no,
                    customer_id=customer.public_id,
                    customer_name=customer.name,
                    status=quotation.status,
                    currency=quotation.currency,
                    subtotal=quotation.subtotal,
                    discount_amount=quotation.discount_amount,
                    tax_amount=quotation.tax_amount,
                    shipping_amount=quotation.shipping_amount,
                    total_amount=quotation.total_amount,
                    valid_until=quotation.valid_until,
                    created_at=quotation.created_at,
                )
                for quotation, customer in rows
            ],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def list_products(
        self,
        principal: Principal,
        *,
        limit: int,
        offset: int,
    ) -> ProductListResponse:
        products, total = await self.repository.list_products(
            principal.tenant_id,
            limit=limit,
            offset=offset,
        )
        return ProductListResponse(
            data=[
                ProductRead(
                    id=product.public_id,
                    sku=product.sku,
                    name=product.name,
                    description=product.description,
                    category=product.category,
                    unit=product.unit,
                    currency=product.currency,
                    base_price=product.base_price,
                    min_order_qty=product.min_order_qty,
                    status=product.status,
                    created_at=product.created_at,
                )
                for product in products
            ],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def create(
        self,
        principal: Principal,
        payload: QuotationCreate,
    ) -> QuotationResponse:
        customer = await self.repository.get_customer(
            principal.tenant_id,
            payload.customer_id,
        )
        if customer is None:
            raise ResourceNotFoundError("Customer")
        if (
            "customer.read_all" not in principal.permissions
            and customer.owner_user_id != principal.user_id
        ):
            raise ResourceNotFoundError("Customer")

        conversation = None
        if payload.conversation_id:
            conversation = await self.repository.get_conversation(
                principal.tenant_id,
                payload.conversation_id,
            )
            if conversation is None:
                raise ResourceNotFoundError("Conversation")
            if conversation.customer_id != customer.id:
                raise ConflictError(
                    "QUOTATION_CUSTOMER_MISMATCH",
                    "Conversation does not belong to the selected customer.",
                )

        requested_products = {
            item.product_id for item in payload.items if item.product_id is not None
        }
        products = await self.repository.get_products(
            principal.tenant_id,
            requested_products,
        )
        if missing := requested_products.difference(products):
            raise ResourceNotFoundError(f"Product {sorted(missing)[0]}")

        quotation_public_id = new_ulid()
        quotation = Quotation(
            public_id=quotation_public_id,
            tenant_id=principal.tenant_id,
            quotation_no=f"Q-{quotation_public_id[-12:]}",
            customer_id=customer.id,
            conversation_id=conversation.id if conversation else None,
            status="pending",
            currency=payload.currency,
            valid_until=payload.valid_until,
            incoterm=payload.incoterm,
            payment_terms=payload.payment_terms,
            notes=payload.notes,
            shipping_amount=self._money(payload.shipping_amount),
            created_by=principal.user_id,
        )

        response_items: list[QuotationItemResponse] = []
        subtotal = Decimal("0")
        discount_amount = Decimal("0")
        tax_amount = Decimal("0")
        for position, item_payload in enumerate(payload.items):
            product = products.get(item_payload.product_id or "")
            if product and product.currency != payload.currency:
                raise ConflictError(
                    "PRODUCT_CURRENCY_MISMATCH",
                    f"Product {product.public_id} is priced in {product.currency}.",
                )
            if (
                product
                and product.min_order_qty is not None
                and item_payload.quantity < product.min_order_qty
            ):
                raise ConflictError(
                    "MINIMUM_ORDER_NOT_MET",
                    f"Product {product.public_id} requires at least {product.min_order_qty}.",
                )
            values = self._item_values(item_payload, product)
            gross = self._money(item_payload.quantity * values["unit_price"])
            item_discount = self._money(gross * item_payload.discount_rate / HUNDRED)
            taxable = gross - item_discount
            item_tax = self._money(taxable * item_payload.tax_rate / HUNDRED)
            line_total = self._money(taxable + item_tax)

            quotation.items.append(
                QuotationItem(
                    product_id=product.id if product else None,
                    sku_snapshot=values["sku"],
                    name_snapshot=values["name"],
                    description=item_payload.description,
                    quantity=item_payload.quantity,
                    unit=values["unit"],
                    unit_price=values["unit_price"],
                    discount_rate=item_payload.discount_rate,
                    tax_rate=item_payload.tax_rate,
                    line_total=line_total,
                    sort_order=position,
                )
            )
            response_items.append(
                QuotationItemResponse(
                    product_id=product.public_id if product else None,
                    sku=values["sku"],
                    name=values["name"],
                    quantity=item_payload.quantity,
                    unit=values["unit"],
                    unit_price=values["unit_price"],
                    discount_rate=item_payload.discount_rate,
                    tax_rate=item_payload.tax_rate,
                    line_total=line_total,
                )
            )
            subtotal += gross
            discount_amount += item_discount
            tax_amount += item_tax

        quotation.subtotal = self._money(subtotal)
        quotation.discount_amount = self._money(discount_amount)
        quotation.tax_amount = self._money(tax_amount)
        quotation.total_amount = self._money(
            quotation.subtotal
            - quotation.discount_amount
            + quotation.tax_amount
            + quotation.shipping_amount
        )
        has_won_history = await self.repository.has_won_quotation(
            principal.tenant_id,
            customer.id,
        )
        self.customer_category.update_customer_category(
            customer,
            source="quotation_created",
            has_won_history=has_won_history,
        )
        self.repository.add(quotation)
        await self.session.commit()
        await self.session.refresh(quotation)
        return QuotationResponse(
            id=quotation.public_id,
            quotation_no=quotation.quotation_no,
            customer_id=customer.public_id,
            conversation_id=conversation.public_id if conversation else None,
            status=quotation.status,
            currency=quotation.currency,
            subtotal=quotation.subtotal,
            discount_amount=quotation.discount_amount,
            tax_amount=quotation.tax_amount,
            shipping_amount=quotation.shipping_amount,
            total_amount=quotation.total_amount,
            valid_until=quotation.valid_until,
            items=response_items,
            created_at=quotation.created_at,
        )

    async def update_status(
        self,
        principal: Principal,
        quotation_id: str,
        payload: QuotationStatusUpdate,
    ) -> QuotationStatusResponse:
        context = await self.repository.get_quotation_with_customer(
            principal.tenant_id,
            quotation_id,
            for_update=True,
        )
        if context is None:
            raise ResourceNotFoundError("Quotation")
        quotation, customer = context
        self._ensure_can_update(principal, quotation)
        if payload.status == "won":
            has_won_history = await self.repository.has_won_quotation(
                principal.tenant_id,
                customer.id,
                exclude_quotation_id=quotation.id,
            )
            self.customer_category.update_customer_category(
                customer,
                source="quotation_won",
                has_won_history=has_won_history,
            )
        quotation.status = payload.status
        await self.session.commit()
        await self.session.refresh(quotation)
        return QuotationStatusResponse(id=quotation.public_id, status=quotation.status)

    async def delete(
        self,
        principal: Principal,
        quotation_id: str,
    ) -> None:
        context = await self.repository.get_quotation_with_customer(
            principal.tenant_id,
            quotation_id,
            for_update=True,
        )
        if context is None:
            raise ResourceNotFoundError("Quotation")
        quotation, _customer = context
        self._ensure_can_update(principal, quotation)
        quotation.deleted_at = datetime.now(UTC)
        await self.session.commit()

    @staticmethod
    def _ensure_can_update(principal: Principal, quotation: Quotation) -> None:
        if (
            "quotation.read_all" not in principal.permissions
            and quotation.created_by != principal.user_id
        ):
            raise ResourceNotFoundError("Quotation")

    def _item_values(
        self,
        payload: QuotationItemCreate,
        product: Product | None,
    ) -> dict[str, str | Decimal]:
        unit_price = payload.unit_price
        if unit_price is None and product is not None:
            unit_price = product.base_price
        if unit_price is None:
            raise ConflictError("UNIT_PRICE_REQUIRED", "Quotation item requires a unit price.")
        return {
            "sku": payload.sku or (product.sku if product else ""),
            "name": payload.name or (product.name if product else ""),
            "unit": payload.unit or (product.unit if product else ""),
            "unit_price": self._money(unit_price),
        }

    @staticmethod
    def _money(value: Decimal) -> Decimal:
        return value.quantize(MONEY, rounding=ROUND_HALF_UP)
