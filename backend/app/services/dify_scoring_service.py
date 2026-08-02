from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import BaseModel, Field, ValidationError, model_validator

from app.core.config import Settings
from app.core.exceptions import ServiceConfigurationError, UpstreamServiceError


class DifyScoreOutput(BaseModel):
    score: int = Field(ge=0, le=100)
    level: str = Field(pattern="^[ABCD]$")
    need_follow: bool
    reason: str = Field(min_length=1, max_length=2000)

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
        try:
            async with httpx.AsyncClient(
                base_url=self.settings.dify_scoring_api_base_url.rstrip("/") + "/",
                timeout=self.settings.dify_scoring_timeout_seconds,
            ) as client:
                response = await client.post("workflows/run", json=payload, headers=headers)
                response.raise_for_status()
                body = response.json()
        except httpx.TimeoutException as exc:
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
            raise UpstreamServiceError(
                "Dify scoring workflow",
                "request failed or returned invalid JSON",
                retryable=status_code in {500, 502, 503},
                upstream_status_code=status_code,
                error_code="DIFY_SCORING_FAILED",
            ) from exc

        try:
            return DifyScoreOutput.model_validate(_extract_output(body))
        except (ValidationError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise UpstreamServiceError(
                "Dify scoring workflow",
                "output must be the configured score JSON object",
                error_code="DIFY_SCORING_OUTPUT_INVALID",
            ) from exc


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
