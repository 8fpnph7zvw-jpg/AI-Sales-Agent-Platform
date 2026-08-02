from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class SalesUserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=10, max_length=128)
    display_name: str = Field(min_length=1, max_length=120)
    sales_name: str = Field(min_length=1, max_length=120)
    feishu_open_id: str | None = Field(default=None, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class SalesUserUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    password: str | None = Field(default=None, min_length=10, max_length=128)
    status: str | None = Field(default=None, pattern="^(active|locked|disabled)$")
    sales_name: str | None = Field(default=None, min_length=1, max_length=120)
    feishu_open_id: str | None = Field(default=None, max_length=128)


class SalesUserRead(BaseModel):
    id: str
    internal_id: int
    email: str
    display_name: str
    status: str
    role: str
    sales_name: str | None
    feishu_open_id: str | None
    created_at: datetime


class SalesUserListResponse(BaseModel):
    data: list[SalesUserRead]
    total: int
