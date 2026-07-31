from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Any

import httpx

from app.core.config import Settings
from app.core.exceptions import ServiceConfigurationError, UpstreamServiceError

logger = logging.getLogger(__name__)

RETRY_DELAYS_SECONDS = (1.0, 3.0, 5.0)


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
    retry_count: int = 0


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
        request_context: dict[str, str | None] | None = None,
    ) -> DifyChatResult:
        context = request_context or {}
        for retry_count in range(len(RETRY_DELAYS_SECONDS) + 1):
            try:
                result = await self._chat_once(
                    query=query,
                    user=user,
                    conversation_id=conversation_id,
                    inputs=inputs,
                )
            except Exception as exc:
                error_code = getattr(exc, "code", type(exc).__name__)
                if not _is_retryable(exc) or retry_count >= len(RETRY_DELAYS_SECONDS):
                    if hasattr(exc, "retry_count"):
                        exc.retry_count = retry_count
                    logger.error(
                        "ai_request_final request_id=%s customer_id=%s conversation_id=%s "
                        "error_code=%s retry_count=%s final_status=failed",
                        context.get("request_id"),
                        context.get("customer_id") or user,
                        context.get("conversation_id") or conversation_id,
                        error_code,
                        retry_count,
                    )
                    raise
                delay = RETRY_DELAYS_SECONDS[retry_count]
                logger.warning(
                    "ai_request_retry request_id=%s customer_id=%s conversation_id=%s "
                    "error_code=%s retry_count=%s final_status=retrying delay_seconds=%s",
                    context.get("request_id"),
                    context.get("customer_id") or user,
                    context.get("conversation_id") or conversation_id,
                    error_code,
                    retry_count + 1,
                    delay,
                )
                await asyncio.sleep(delay)
                continue

            result = replace(result, retry_count=retry_count)
            logger.info(
                "ai_request_final request_id=%s customer_id=%s conversation_id=%s "
                "error_code=none retry_count=%s final_status=succeeded",
                context.get("request_id"),
                context.get("customer_id") or user,
                context.get("conversation_id") or conversation_id,
                retry_count,
            )
            return result

        raise RuntimeError("Dify retry loop terminated unexpectedly")

    async def _chat_once(
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
            "response_mode": "streaming",
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
            "query_length=%s input_keys=%s "
            "conversation_id_present=%s response_mode=streaming",
            base_url,
            user,
            len(query),
            sorted(inputs),
            bool(conversation_id),
        )
        try:
            async with httpx.AsyncClient(
                base_url=base_url,
                timeout=self.settings.dify_timeout_seconds,
            ) as client:
                async with client.stream(
                    "POST",
                    "chat-messages",
                    json=payload,
                    headers=headers,
                ) as response:
                    if response.status_code >= 400:
                        await response.aread()
                    response.raise_for_status()
                    data = await _read_streaming_chat_response(response)
        except httpx.TimeoutException as exc:
            raise UpstreamServiceError(
                "Dify",
                "request timed out",
                retryable=True,
                error_code="DIFY_TIMEOUT",
            ) from exc
        except httpx.HTTPStatusError as exc:
            response_text = exc.response.text
            logger.error(
                "Dify API error:\nstatus_code=%s\nresponse.text=%s",
                exc.response.status_code,
                response_text[:4000],
            )
            if exc.response.status_code == 401:
                raise UpstreamServiceError(
                    "Dify",
                    "authentication failed (HTTP 401). DIFY_API_KEY must be the "
                    "App API key for the application serving /chat-messages, "
                    "not a Dataset/Knowledge key.",
                    upstream_status_code=401,
                    error_code="DIFY_HTTP_401",
                ) from exc
            raise UpstreamServiceError(
                "Dify",
                (
                    f"returned HTTP {exc.response.status_code}: "
                    f"{response_text[:1000]}"
                ),
                retryable=exc.response.status_code in {500, 502, 503},
                upstream_status_code=exc.response.status_code,
                error_code=f"DIFY_HTTP_{exc.response.status_code}",
            ) from exc
        except httpx.HTTPError as exc:
            raise UpstreamServiceError(
                "Dify",
                "request failed",
                retryable=True,
                error_code="DIFY_NETWORK_ERROR",
            ) from exc

        answer = str(data.get("answer") or "").strip()
        if not answer:
            raise UpstreamServiceError(
                "Dify",
                "response did not contain an answer",
                retryable=True,
                error_code="DIFY_EMPTY_RESPONSE",
            )
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


async def _read_streaming_chat_response(response: httpx.Response) -> dict[str, Any]:
    answer_parts: list[str] = []
    result: dict[str, Any] = {}
    metadata: dict[str, Any] = {}

    async for sse_event, raw_data in _iter_sse_events(response):
        if raw_data == "[DONE]":
            continue
        try:
            data = json.loads(raw_data)
        except json.JSONDecodeError as exc:
            raise UpstreamServiceError(
                "Dify",
                "returned malformed SSE data",
                retryable=True,
                error_code="DIFY_STREAM_ERROR",
            ) from exc
        if not isinstance(data, dict):
            continue

        event = str(data.get("event") or sse_event or "")
        if event in {"message", "agent_message"}:
            answer_parts.append(str(data.get("answer") or ""))
        elif event == "error":
            message = str(data.get("message") or data.get("code") or "streaming request failed")
            raise UpstreamServiceError(
                "Dify",
                message,
                retryable=True,
                error_code="DIFY_STREAM_ERROR",
            )

        for key in ("conversation_id", "task_id"):
            if data.get(key):
                result[key] = data[key]
        if data.get("message_id"):
            result["message_id"] = data["message_id"]
        elif data.get("id") and not result.get("message_id"):
            result["message_id"] = data["id"]

        event_metadata = data.get("metadata")
        if isinstance(event_metadata, dict):
            metadata.update(event_metadata)

    result["answer"] = "".join(answer_parts)
    result["metadata"] = metadata
    return result


async def _iter_sse_events(response: httpx.Response) -> AsyncIterator[tuple[str | None, str]]:
    event_name: str | None = None
    data_lines: list[str] = []

    async for line in response.aiter_lines():
        if not line:
            if data_lines:
                yield event_name, "\n".join(data_lines)
            event_name = None
            data_lines = []
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event_name = line[6:].lstrip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].lstrip())

    if data_lines:
        yield event_name, "\n".join(data_lines)


def dify_key_type(value: str) -> str:
    normalized = value.strip().lower()
    if normalized.startswith("app-"):
        return "app"
    if normalized.startswith(("dataset-", "knowledge-")):
        return "dataset"
    return "unknown" if normalized else "missing"


def _is_retryable(exc: Exception) -> bool:
    return isinstance(exc, UpstreamServiceError) and exc.retryable
