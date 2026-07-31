from __future__ import annotations

import asyncio
import logging
import os
import socket
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select

from app.connectors.whatsapp.repository import WhatsAppRepository
from app.connectors.whatsapp.service import WhatsAppService
from app.core.config import get_settings
from app.core.encryption import ConfigCipher
from app.db.session import AsyncSessionLocal
from app.integrations.dify.client import DifyClient
from app.models.connector.webhook_log import WebhookLog
from app.models.system.outbox_event import OutboxEvent

logger = logging.getLogger(__name__)
EVENT_TYPE = "ai.whatsapp.retry.requested.v1"
WORKER_ID = f"{socket.gethostname()}:{os.getpid()}:whatsapp-ai-retry"


async def run_whatsapp_ai_retry_worker(stop_event: asyncio.Event) -> None:
    settings = get_settings()
    logger.info("whatsapp_ai_retry_worker_started worker_id=%s", WORKER_ID)
    while not stop_event.is_set():
        try:
            processed = await _process_next_event()
        except asyncio.CancelledError:
            raise
        except Exception:
            processed = False
            logger.exception("whatsapp_ai_retry_worker_iteration_failed worker_id=%s", WORKER_ID)
        if processed:
            continue
        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=settings.whatsapp_ai_retry_poll_seconds,
            )
        except TimeoutError:
            pass
    logger.info("whatsapp_ai_retry_worker_stopped worker_id=%s", WORKER_ID)


async def _process_next_event() -> bool:
    event_id: int | None = None
    payload: dict[str, object] = {}
    now = datetime.now(UTC)
    stale_before = now - timedelta(minutes=5)
    async with AsyncSessionLocal() as session:
        async with session.begin():
            event = await session.scalar(
                select(OutboxEvent)
                .where(
                    OutboxEvent.event_type == EVENT_TYPE,
                    or_(
                        (
                            (OutboxEvent.status == "pending")
                            & (OutboxEvent.available_at <= now)
                        ),
                        (
                            (OutboxEvent.status == "processing")
                            & (OutboxEvent.locked_at < stale_before)
                        ),
                    ),
                )
                .order_by(OutboxEvent.available_at, OutboxEvent.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if event is None:
                return False
            event.status = "processing"
            event.locked_at = now
            event.locked_by = WORKER_ID
            event_id = event.id
            payload = dict(event.payload)

    webhook_log_id = str(payload.get("webhook_log_id") or "")
    try:
        async with AsyncSessionLocal() as session:
            settings = get_settings()
            service = WhatsAppService(
                session,
                WhatsAppRepository(session),
                settings,
                ConfigCipher(settings),
                DifyClient(settings),
            )
            await service.retry_pending_webhook(webhook_log_id)
    except asyncio.CancelledError:
        await _release_event(event_id, payload, "worker cancelled")
        raise
    except Exception as exc:
        await _release_event(event_id, payload, str(exc)[:1000])
        logger.error(
            "whatsapp_ai_background_retry request_id=%s customer_id=%s "
            "conversation_id=%s error_code=%s retry_count=%s "
            "final_status=pending_background",
            payload.get("request_id"),
            payload.get("customer_id"),
            payload.get("conversation_id"),
            getattr(exc, "code", type(exc).__name__),
            getattr(exc, "retry_count", 0),
            exc_info=True,
        )
        return True

    async with AsyncSessionLocal() as session:
        async with session.begin():
            event = await session.get(OutboxEvent, event_id, with_for_update=True)
            if event is not None:
                event.status = "published"
                event.published_at = datetime.now(UTC)
                event.locked_at = None
                event.locked_by = None
                event.last_error = None
                event.payload = {**event.payload, "final_status": "succeeded"}
    logger.info(
        "whatsapp_ai_background_retry request_id=%s customer_id=%s "
        "conversation_id=%s error_code=none retry_count=%s final_status=succeeded",
        payload.get("request_id"),
        payload.get("customer_id"),
        payload.get("conversation_id"),
        payload.get("retry_count", 0),
    )
    return True


async def _release_event(
    event_id: int | None,
    payload: dict[str, object],
    error_message: str,
) -> None:
    if event_id is None:
        return
    settings = get_settings()
    async with AsyncSessionLocal() as session:
        async with session.begin():
            event = await session.get(OutboxEvent, event_id, with_for_update=True)
            if event is None:
                return
            event.attempt_count += 1
            delay = min(
                30 * (2 ** min(event.attempt_count - 1, 4)),
                settings.whatsapp_ai_retry_max_delay_seconds,
            )
            next_retry_at = datetime.now(UTC) + timedelta(seconds=delay)
            event.status = "pending"
            event.available_at = next_retry_at
            event.locked_at = None
            event.locked_by = None
            event.last_error = error_message
            event.payload = {
                **event.payload,
                "retry_count": event.attempt_count,
                "final_status": "pending_background",
            }
            webhook_log_id = str(payload.get("webhook_log_id") or "")
            webhook_log = await session.scalar(
                select(WebhookLog)
                .where(WebhookLog.public_id == webhook_log_id)
                .with_for_update()
            )
            if webhook_log is not None:
                if webhook_log.status == "processed":
                    event.status = "published"
                    event.published_at = datetime.now(UTC)
                    event.last_error = None
                    event.payload = {**event.payload, "final_status": "succeeded"}
                else:
                    webhook_log.status = "retry_pending"
                    webhook_log.next_retry_at = next_retry_at
