from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator


class QuotationItemCreate(BaseModel):
    product_id: str | None = Field(default=None, min_length=26, max_length=26)
    sku: str | None = Field(default=None, max_length=120)
    name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    quantity: Decimal = Field(gt=0, max_digits=19, decimal_places=4)
    unit: str | None = Field(default=None, max_length=32)
    unit_price: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=19,
        decimal_places=4,
    )
    discount_rate: Decimal = Field(
        default=Decimal("0"),
        ge=0,
        le=100,
        max_digits=7,
        decimal_places=4,
    )
    tax_rate: Decimal = Field(
        default=Decimal("0"),
        ge=0,
        le=100,
        max_digits=7,
        decimal_places=4,
    )

    @model_validator(mode="after")
    def validate_manual_item(self) -> QuotationItemCreate:
        if self.product_id is None and not all(
            (self.sku, self.name, self.unit, self.unit_price is not None)
        ):
            raise ValueError("sku, name, unit, and unit_price are required without product_id")
        return self


class QuotationCreate(BaseModel):
    customer_id: str = Field(min_length=26, max_length=26)
    conversation_id: str | None = Field(default=None, min_length=26, max_length=26)
    currency: str = Field(min_length=3, max_length=3)
    valid_until: date | None = None
    incoterm: str | None = Field(default=None, max_length=16)
    payment_terms: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=5000)
    shipping_amount: Decimal = Field(
        default=Decimal("0"),
        ge=0,
        max_digits=19,
        decimal_places=4,
    )
    items: list[QuotationItemCreate] = Field(min_length=1, max_length=200)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


class QuotationItemResponse(BaseModel):
    product_id: str | None
    sku: str
    name: str
    quantity: Decimal
    unit: str
    unit_price: Decimal
    discount_rate: Decimal
    tax_rate: Decimal
    line_total: Decimal


class QuotationResponse(BaseModel):
    id: str
    quotation_no: str
    customer_id: str
    conversation_id: str | None
    status: str
    currency: str
    subtotal: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    shipping_amount: Decimal
    total_amount: Decimal
    valid_until: date | None
    items: list[QuotationItemResponse]
    created_at: datetime
