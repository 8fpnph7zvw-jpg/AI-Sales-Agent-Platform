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
    level: str = Field(default="", pattern="^[ABC]$")
    need_follow: bool
    reason: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="before")
    @classmethod
    def calculate_level_from_score(cls, values: Any) -> Any:
        if isinstance(values, dict) and "score" in values:
            normalized = dict(values)
            try:
                normalized["level"] = score_level(int(normalized["score"]))
            except (TypeError, ValueError):
                pass
            return normalized
        return values

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

@dataclass(frozen=True, slots=True)
class DifyScoringInput:
    chat_history: str
    customer_profile: str
    product_requirement: str
    quantity: str
    country: str
    user: str


def score_level(score: int) -> str:
    if score >= 70:
        return "A"
    if score >= 31:
        return "B"
    return "C"


class DifyScoringService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def configured(self) -> bool:
        return bool(self.settings.dify_scoring_api_key)

    async def run(self, scoring_input: DifyScoringInput) -> DifyScoreOutput:
        if not self.settings.dify_scoring_api_key:
            raise ServiceConfigurationError("DIFY_SCORING_API_KEY is not configured.")
        conversation_history = (
            f"客户聊天记录:\n{scoring_input.chat_history}\n\n"
            f"客户资料:\n{scoring_input.customer_profile}\n\n"
            f"产品需求:\n{scoring_input.product_requirement}\n\n"
            f"数量:\n{scoring_input.quantity}\n\n"
            f"国家:\n{scoring_input.country}"
        )
        payload = {
            "inputs": {
                "conversation_history": conversation_history,
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
        except httpx.HTTPError as exc:
            logger.warning(
                "dify_scoring_request_failed customer_id=%s status_code=none "
                "content_type=none response_summary=none error=%s",
                scoring_input.user,
                type(exc).__name__,
            )
            raise UpstreamServiceError(
                "Dify scoring workflow",
                "request failed",
                retryable=True,
                error_code="DIFY_SCORING_FAILED",
            ) from exc

        content_type = response.headers.get("content-type", "")
        response_summary = _response_summary(response)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "dify_scoring_http_error customer_id=%s status_code=%s "
                "content_type=%s response_summary=%s",
                scoring_input.user,
                response.status_code,
                content_type or "none",
                response_summary,
            )
            raise UpstreamServiceError(
                "Dify scoring workflow",
                f"returned HTTP {response.status_code}",
                retryable=response.status_code in {500, 502, 503},
                upstream_status_code=response.status_code,
                error_code=f"DIFY_SCORING_HTTP_{response.status_code}",
            ) from exc

        try:
            body = response.json()
        except ValueError as exc:
            logger.warning(
                "dify_scoring_invalid_json customer_id=%s status_code=%s "
                "content_type=%s response_summary=%s",
                scoring_input.user,
                response.status_code,
                content_type or "none",
                response_summary,
            )
            raise UpstreamServiceError(
                "Dify scoring workflow",
                "returned invalid JSON",
                upstream_status_code=response.status_code,
                error_code="DIFY_SCORING_INVALID_JSON",
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
        for key in (
            "structured_output",
            "score_result",
            "result",
            "output",
            "text",
            "json",
        ):
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


def _response_summary(response: httpx.Response, *, limit: int = 1000) -> str:
    summary = " ".join(response.text.split())
    return summary[:limit] if summary else "<empty>"
