from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from app.core.config import Settings
from app.core.exceptions import ServiceConfigurationError, UpstreamServiceError

logger = logging.getLogger(__name__)


class DifyScoreOutput(BaseModel):
    score: int = Field(ge=0, le=100)
    level: str = Field(pattern="^[ABCD]$")
    need_follow: bool
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("need_follow", mode="before")
    @classmethod
    def normalize_need_follow(cls, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and value in {0, 1}:
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "yes", "y", "1", "是", "需要"}:
                return True
            if normalized in {"false", "no", "n", "0", "否", "不需要"}:
                return False
        raise ValueError("need_follow must be a boolean or a supported boolean label")

    @model_validator(mode="after")
    def validate_level(self) -> DifyScoreOutput:
        expected = score_level(self.score)
        if self.level != expected:
            raise ValueError(f"level must be {expected} when score is {self.score}")
        return self


@dataclass(frozen=True, slots=True)
class DifyScoringInput:
    chat_history: str
    customer_profile: str
    product_requirement: str
    quantity: str
    country: str
    user: str


def score_level(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 70:
        return "B"
    if score >= 40:
        return "C"
    return "D"


class DifyScoringService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def configured(self) -> bool:
        return bool(self.settings.dify_scoring_api_key)

    async def run(self, scoring_input: DifyScoringInput) -> DifyScoreOutput:
        if not self.settings.dify_scoring_api_key:
            raise ServiceConfigurationError("DIFY_SCORING_API_KEY is not configured.")
        payload = {
            "inputs": {
                "chat_history": scoring_input.chat_history,
                "customer_profile": scoring_input.customer_profile,
                "product_requirement": scoring_input.product_requirement,
                "quantity": scoring_input.quantity,
                "country": scoring_input.country,
            },
            "response_mode": "blocking",
            "user": scoring_input.user,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.dify_scoring_api_key}",
            "Content-Type": "application/json",
        }
        workflow_url = self.settings.dify_scoring_api_base_url.rstrip("/") + "/workflows/run"
        logger.info(
            "dify_scoring_request url=%s customer_id=%s chat_length=%s",
            workflow_url,
            scoring_input.user,
            len(scoring_input.chat_history),
        )
        try:
            async with httpx.AsyncClient(
                base_url=self.settings.dify_scoring_api_base_url.rstrip("/") + "/",
                timeout=self.settings.dify_scoring_timeout_seconds,
            ) as client:
                response = await client.post("workflows/run", json=payload, headers=headers)
                response.raise_for_status()
                body = response.json()
        except httpx.TimeoutException as exc:
            logger.warning(
                "dify_scoring_timeout customer_id=%s",
                scoring_input.user,
            )
            raise UpstreamServiceError(
                "Dify scoring workflow",
                "request timed out",
                retryable=True,
                error_code="DIFY_SCORING_TIMEOUT",
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            status_code = (
                exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
            )
            logger.warning(
                "dify_scoring_request_failed customer_id=%s status_code=%s error=%s",
                scoring_input.user,
                status_code,
                type(exc).__name__,
            )
            raise UpstreamServiceError(
                "Dify scoring workflow",
                "request failed or returned invalid JSON",
                retryable=status_code in {500, 502, 503},
                upstream_status_code=status_code,
                error_code="DIFY_SCORING_FAILED",
            ) from exc

        try:
            output = DifyScoreOutput.model_validate(_extract_output(body))
        except (ValidationError, TypeError, ValueError, json.JSONDecodeError) as exc:
            logger.warning(
                "dify_scoring_output_invalid customer_id=%s body_keys=%s error=%s",
                scoring_input.user,
                sorted(body) if isinstance(body, dict) else [],
                type(exc).__name__,
            )
            raise UpstreamServiceError(
                "Dify scoring workflow",
                "output must be the configured score JSON object",
                error_code="DIFY_SCORING_OUTPUT_INVALID",
            ) from exc
        logger.info(
            "dify_scoring_succeeded customer_id=%s score=%s level=%s need_follow=%s",
            scoring_input.user,
            output.score,
            output.level,
            output.need_follow,
        )
        return output


def _extract_output(body: dict[str, Any]) -> dict[str, Any]:
    data = body.get("data") if isinstance(body.get("data"), dict) else body
    outputs = data.get("outputs") if isinstance(data, dict) else None
    candidate: Any = outputs
    if isinstance(outputs, dict) and not {"score", "level", "need_follow", "reason"}.issubset(
        outputs
    ):
        for key in ("result", "output", "text", "json"):
            if key in outputs:
                candidate = outputs[key]
                break
    if isinstance(candidate, str):
        candidate = json.loads(
            candidate.strip().removeprefix("```json").removesuffix("```").strip()
        )
    if not isinstance(candidate, dict):
        raise TypeError("Workflow outputs are not an object")
    return candidate
