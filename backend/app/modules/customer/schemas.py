from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    company_name: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=254)
    phone_e164: str | None = Field(default=None, max_length=32)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    language: str | None = Field(default=None, max_length=16)
    source_type: str | None = Field(default=None, max_length=64)
    source_ref: str | None = Field(default=None, max_length=255)
    tags: list[str] = Field(default_factory=list, max_length=50)
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        return value.strip().lower() if value else None

    @field_validator("country_code")
    @classmethod
    def normalize_country(cls, value: str | None) -> str | None:
        return value.upper() if value else None


class CustomerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    public_id: str = Field(serialization_alias="id")
    name: str
    company_name: str | None
    email: str | None
    phone_e164: str | None
    country_code: str | None
    language: str | None
    lifecycle_stage: str
    intent_score: Decimal | None
    intent_level: str | None
    score_explanation: dict[str, Any] | None
    source_type: str | None
    source_ref: str | None
    tags: list[str]
    owner_user_id: int | None
    do_not_contact: bool
    last_contact_at: datetime | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class CustomerListResponse(BaseModel):
    data: list[CustomerRead]
    total: int
    limit: int
    offset: int
