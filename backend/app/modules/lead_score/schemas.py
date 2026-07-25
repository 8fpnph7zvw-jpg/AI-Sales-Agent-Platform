from __future__ import annotations

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
