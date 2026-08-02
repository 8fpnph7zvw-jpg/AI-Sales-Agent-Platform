from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import Principal
from app.core.exceptions import ResourceNotFoundError
from app.modules.lead_score.repository import LeadScoreRepository
from app.modules.lead_score.schemas import (
    CustomerScoreListResponse,
    CustomerScoreRead,
    LeadScoreRequest,
    LeadScoreResponse,
)

SCORING_VERSION = "rules-v1"
WEIGHTS = {
    "need_clarity": 0.25,
    "budget_match": 0.20,
    "urgency": 0.20,
    "engagement": 0.15,
    "profile_fit": 0.20,
}


class LeadScoreService:
    def __init__(
        self,
        session: AsyncSession,
        repository: LeadScoreRepository,
    ) -> None:
        self.session = session
        self.repository = repository

    async def score(
        self,
        principal: Principal,
        payload: LeadScoreRequest,
    ) -> LeadScoreResponse:
        customer = await self.repository.get_customer_for_update(
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

        components = payload.signals.model_dump()
        score = round(
            sum(components[name] * weight for name, weight in WEIGHTS.items()),
            2,
        )
        level = self._level(score)
        customer.intent_score = Decimal(str(score))
        customer.intent_level = level
        customer.score_explanation = {
            "version": SCORING_VERSION,
            "weights": WEIGHTS,
            "components": components,
        }
        await self.session.commit()
        return LeadScoreResponse(
            customer_id=customer.public_id,
            score=score,
            level=level,
            components=components,
            scoring_version=SCORING_VERSION,
        )

    async def list_scores(
        self,
        principal: Principal,
        *,
        customer_id: str | None,
        limit: int,
        offset: int,
    ) -> CustomerScoreListResponse:
        rows, total = await self.repository.list_scores(
            principal.tenant_id,
            owner_user_id=(
                None if "customer.read_all" in principal.permissions else principal.user_id
            ),
            customer_public_id=customer_id,
            limit=limit,
            offset=offset,
        )
        return CustomerScoreListResponse(
            data=[
                CustomerScoreRead(
                    id=score.id,
                    customer_id=customer.public_id,
                    customer_name=customer.name,
                    score=score.score,
                    level=score.level,
                    need_follow=score.need_follow,
                    reason=score.reason,
                    created_time=score.created_time,
                )
                for score, customer in rows
            ],
            total=total,
            limit=limit,
            offset=offset,
        )

    @staticmethod
    def _level(score: float) -> str:
        if score >= 80:
            return "hot"
        if score >= 60:
            return "warm"
        if score >= 40:
            return "nurture"
        return "cold"
