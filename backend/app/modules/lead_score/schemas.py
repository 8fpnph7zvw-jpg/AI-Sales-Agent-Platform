from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class LeadScoreSignals(BaseModel):
    need_clarity: float = Field(ge=0, le=100)
    budget_match: float = Field(ge=0, le=100)
    urgency: float = Field(ge=0, le=100)
    engagement: float = Field(ge=0, le=100)
    profile_fit: float = Field(ge=0, le=100)


class LeadScoreRequest(BaseModel):
    customer_id: str = Field(min_length=26, max_length=26)
    signals: LeadScoreSignals


class LeadScoreResponse(BaseModel):
    customer_id: str
    score: float
    level: str
    components: dict[str, float]
    scoring_version: str


class WorkflowScoreRequest(BaseModel):
    customer_id: str = Field(min_length=26, max_length=26)
    product_requirement: str | None = Field(default=None, max_length=2000)
    quantity: str | None = Field(default=None, max_length=120)


class CustomerScoreRead(BaseModel):
    id: int
    customer_id: str
    customer_name: str
    score: int
    level: str
    need_follow: bool
    reason: str
    created_time: datetime


class CustomerScoreListResponse(BaseModel):
    data: list[CustomerScoreRead]
    total: int
    limit: int
    offset: int


class CustomerCurrentScoreRead(BaseModel):
    customer_id: str
    customer_name: str
    intent_score: Decimal | None
    intent_level: str | None
    category: str
    last_scored_at: datetime | None


class CustomerCurrentScoreListResponse(BaseModel):
    data: list[CustomerCurrentScoreRead]
    total: int
    limit: int
    offset: int
