from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import httpx

from app.core.config import Settings
from app.core.exceptions import ServiceConfigurationError, UpstreamServiceError

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DifyChatResult:
    answer: str
    conversation_id: str | None
    task_id: str | None
    message_id: str | None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_price: Decimal | None = None
    currency: str | None = None
    latency_ms: int | None = None
    citations: list[dict[str, Any]] = field(default_factory=list)
    raw_metadata: dict[str, Any] = field(default_factory=dict)


class DifyClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def chat(
        self,
        *,
        query: str,
        user: str,
        conversation_id: str | None,
        inputs: dict[str, Any],
    ) -> DifyChatResult:
        if not self.settings.dify_api_key:
            raise ServiceConfigurationError("DIFY_API_KEY is not configured.")
        if dify_key_type(self.settings.dify_api_key) == "dataset":
            raise ServiceConfigurationError(
                "DIFY_API_KEY is a Dataset/Knowledge API key. "
                "Configure the App API key from the Dify application's API Access page."
            )

        payload = {
            "inputs": inputs,
            "query": query,
            "response_mode": "blocking",
            "conversation_id": conversation_id or "",
            "user": user,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.dify_api_key}",
            "Content-Type": "application/json",
        }
        base_url = self.settings.dify_api_base_url.rstrip("/") + "/"
        logger.info(
            "dify_chat_request url=%schat-messages user=%s "
            "query_length=%s conversation_id_present=%s",
            base_url,
            user,
            len(query),
            bool(conversation_id),
        )
        try:
            async with httpx.AsyncClient(
                base_url=base_url,
                timeout=self.settings.dify_timeout_seconds,
            ) as client:
                response = await client.post("chat-messages", json=payload, headers=headers)
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise UpstreamServiceError("Dify", "request timed out") from exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 401:
                raise UpstreamServiceError(
                    "Dify",
                    "authentication failed (HTTP 401). DIFY_API_KEY must be the "
                    "App API key for the application serving /chat-messages, "
                    "not a Dataset/Knowledge key.",
                ) from exc
            raise UpstreamServiceError(
                "Dify",
                f"returned HTTP {exc.response.status_code}",
            ) from exc
        except httpx.HTTPError as exc:
            raise UpstreamServiceError("Dify", "request failed") from exc

        data = response.json()
        answer = str(data.get("answer") or "").strip()
        if not answer:
            raise UpstreamServiceError("Dify", "response did not contain an answer")
        logger.info(
            "dify_chat_response status=success answer_length=%s "
            "conversation_id_present=%s",
            len(answer),
            bool(data.get("conversation_id")),
        )

        metadata = data.get("metadata") or {}
        usage = metadata.get("usage") or {}
        retriever_resources = metadata.get("retriever_resources") or []
        latency = usage.get("latency")
        total_price = usage.get("total_price")
        return DifyChatResult(
            answer=answer,
            conversation_id=data.get("conversation_id"),
            task_id=data.get("task_id"),
            message_id=data.get("message_id") or data.get("id"),
            prompt_tokens=_optional_int(usage.get("prompt_tokens")),
            completion_tokens=_optional_int(usage.get("completion_tokens")),
            total_price=Decimal(str(total_price)) if total_price is not None else None,
            currency=usage.get("currency"),
            latency_ms=int(float(latency) * 1000) if latency is not None else None,
            citations=list(retriever_resources),
            raw_metadata=metadata,
        )


def _optional_int(value: Any) -> int | None:
    return int(value) if value is not None else None


def dify_key_type(value: str) -> str:
    normalized = value.strip().lower()
    if normalized.startswith("app-"):
        return "app"
    if normalized.startswith(("dataset-", "knowledge-")):
        return "dataset"
    return "unknown" if normalized else "missing"
