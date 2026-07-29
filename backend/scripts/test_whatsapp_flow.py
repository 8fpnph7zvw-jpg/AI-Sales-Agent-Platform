from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

import httpx


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name, "").strip()
    runtime_files = {
        "OPENWA_API_KEY": Path("/run/openwa/openwa_api_key"),
        "OPENWA_SESSION": Path("/run/openwa/openwa_session"),
    }
    runtime_file = runtime_files.get(name)
    if not value and runtime_file is not None and runtime_file.is_file():
        value = runtime_file.read_text(encoding="utf-8").strip()
    return value or default


def _required(name: str) -> str:
    value = _env(name)
    if not value:
        raise RuntimeError(f"{name} is required for this check")
    return value


def _openwa_headers() -> dict[str, str]:
    return {
        "x-api-key": _required("OPENWA_API_KEY"),
        "Content-Type": "application/json",
    }


def _chat_id(value: str) -> str:
    if "@" in value:
        return value
    digits = "".join(character for character in value if character.isdigit())
    if not digits:
        raise RuntimeError("A valid --phone value is required")
    return f"{digits}@c.us"


async def check_openwa_health(client: httpx.AsyncClient) -> None:
    openwa_url = _env("OPENWA_URL", "http://openwa:2785/api").rstrip("/")
    response = await client.get(f"{openwa_url}/health/ready")
    response.raise_for_status()
    print("openwa_health:", response.json())

    api_key = _env("OPENWA_API_KEY")
    if api_key:
        sessions = await client.get(
            f"{openwa_url}/sessions",
            headers=_openwa_headers(),
        )
        sessions.raise_for_status()
        print("openwa_sessions:", json.dumps(sessions.json(), ensure_ascii=False))


async def send_test_message(
    client: httpx.AsyncClient,
    *,
    phone: str,
    message: str,
) -> None:
    openwa_url = _env("OPENWA_URL", "http://openwa:2785/api").rstrip("/")
    session_id = _required("OPENWA_SESSION")
    response = await client.post(
        f"{openwa_url}/sessions/{session_id}/messages/send-text",
        headers=_openwa_headers(),
        json={"chatId": _chat_id(phone), "text": message},
    )
    response.raise_for_status()
    print("openwa_send:", response.json())


async def simulate_webhook(
    client: httpx.AsyncClient,
    *,
    phone: str,
    message: str,
) -> None:
    backend_url = _env(
        "BACKEND_API_URL",
        "http://backend:8000/api/v1",
    ).rstrip("/")
    session_id = _required("OPENWA_SESSION")
    api_key = _required("OPENWA_API_KEY")
    message_id = f"flow-test-{uuid.uuid4().hex}"
    now = int(time.time())
    payload: dict[str, Any] = {
        "event": "message.received",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "sessionId": session_id,
        "idempotencyKey": f"openwa:{session_id}:message.received:{message_id}",
        "deliveryId": str(uuid.uuid4()),
        "data": {
            "id": message_id,
            "from": _chat_id(phone),
            "to": session_id,
            "body": message,
            "type": "text",
            "timestamp": now,
            "senderPhone": _chat_id(phone),
            "hasMedia": False,
        },
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    signature = hmac.new(api_key.encode(), body, hashlib.sha256).hexdigest()
    response = await client.post(
        f"{backend_url}/webhooks/whatsapp",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-OpenWA-Signature": f"sha256={signature}",
            "X-OpenWA-Delivery-Id": payload["deliveryId"],
        },
    )
    response.raise_for_status()
    print("whatsapp_webhook:", response.json())


async def check_dify(
    client: httpx.AsyncClient,
    *,
    query: str,
) -> None:
    base_url = _env("DIFY_API_BASE_URL", "https://api.dify.ai/v1").rstrip("/")
    api_key = _required("DIFY_API_KEY")
    if api_key.lower().startswith(("dataset-", "knowledge-")):
        raise RuntimeError(
            "DIFY_API_KEY is a Dataset/Knowledge key; use the App API key"
        )
    response = await client.post(
        f"{base_url}/chat-messages",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "inputs": {},
            "query": query,
            "response_mode": "blocking",
            "conversation_id": "",
            "user": "ai-sales-agent-flow-test",
        },
    )
    response.raise_for_status()
    data = response.json()
    print(
        "dify_chat:",
        {
            "answer": data.get("answer"),
            "conversation_id": data.get("conversation_id"),
        },
    )


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run AI Sales Agent WhatsApp/Dify flow checks.",
    )
    parser.add_argument(
        "checks",
        nargs="+",
        choices=("health", "send", "webhook", "dify"),
    )
    parser.add_argument("--phone", default="")
    parser.add_argument("--message", default="WhatsApp connector test")
    parser.add_argument("--query", default="风衣")
    args = parser.parse_args()

    async with httpx.AsyncClient(timeout=60) as client:
        for check in args.checks:
            if check == "health":
                await check_openwa_health(client)
            elif check == "send":
                await send_test_message(
                    client,
                    phone=args.phone,
                    message=args.message,
                )
            elif check == "webhook":
                await simulate_webhook(
                    client,
                    phone=args.phone,
                    message=args.message,
                )
            elif check == "dify":
                await check_dify(client, query=args.query)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except httpx.HTTPStatusError as exc:
        body = exc.response.text[:1000]
        raise SystemExit(
            f"HTTP {exc.response.status_code} from {exc.request.url}: {body}"
        ) from exc
    except (httpx.HTTPError, RuntimeError) as exc:
        raise SystemExit(str(exc)) from exc
