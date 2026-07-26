from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import Principal, require_any_permission
from app.connectors.whatsapp.repository import WhatsAppRepository
from app.connectors.whatsapp.schemas import (
    WhatsAppConfigStatusResponse,
    WhatsAppTestRequest,
    WhatsAppTestResponse,
    WhatsAppWebhookPayload,
    WhatsAppWebhookResponse,
)
from app.connectors.whatsapp.service import WhatsAppService
from app.core.config import get_settings
from app.core.encryption import ConfigCipher
from app.core.exceptions import AppError
from app.db.session import get_db
from app.integrations.dify.client import DifyClient

webhook_router = APIRouter(prefix="/webhooks/whatsapp", tags=["WhatsApp Webhook"])
management_router = APIRouter(prefix="/connectors/whatsapp", tags=["WhatsApp Connector"])


def get_whatsapp_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> WhatsAppService:
    settings = get_settings()
    return WhatsAppService(
        session,
        WhatsAppRepository(session),
        settings,
        ConfigCipher(settings),
        DifyClient(settings),
    )


@webhook_router.get("", response_class=PlainTextResponse)
async def verify_whatsapp_webhook(
    service: Annotated[WhatsAppService, Depends(get_whatsapp_service)],
    hub_mode: Annotated[str | None, Query(alias="hub.mode")] = None,
    hub_verify_token: Annotated[str | None, Query(alias="hub.verify_token")] = None,
    hub_challenge: Annotated[str | None, Query(alias="hub.challenge")] = None,
) -> str:
    return await service.verify_subscription(
        mode=hub_mode,
        verify_token=hub_verify_token,
        challenge=hub_challenge,
    )


@webhook_router.post("", response_model=WhatsAppWebhookResponse)
async def receive_whatsapp_webhook(
    request: Request,
    service: Annotated[WhatsAppService, Depends(get_whatsapp_service)],
) -> WhatsAppWebhookResponse:
    raw_body = await request.body()
    if len(raw_body) > get_settings().whatsapp_webhook_max_bytes:
        raise AppError(
            413,
            "WHATSAPP_PAYLOAD_TOO_LARGE",
            "WhatsApp webhook payload exceeds the configured size limit.",
        )
    try:
        payload_dict = json.loads(raw_body)
        if not isinstance(payload_dict, dict):
            raise ValueError
        payload = WhatsAppWebhookPayload.model_validate(payload_dict)
    except (json.JSONDecodeError, UnicodeDecodeError, ValidationError, ValueError) as exc:
        raise AppError(
            422,
            "WHATSAPP_PAYLOAD_INVALID",
            "WhatsApp webhook payload is invalid.",
        ) from exc
    return await service.handle_webhook(
        raw_body=raw_body,
        payload=payload,
        payload_dict=payload_dict,
        headers={key.lower(): value for key, value in request.headers.items()},
    )


@management_router.get(
    "/{connector_id}/config-status",
    response_model=WhatsAppConfigStatusResponse,
)
async def whatsapp_config_status(
    connector_id: str,
    request: Request,
    service: Annotated[WhatsAppService, Depends(get_whatsapp_service)],
    principal: Annotated[
        Principal,
        Depends(require_any_permission("connector.read", "connector.manage")),
    ],
) -> WhatsAppConfigStatusResponse:
    webhook_url = (
        str(request.base_url).rstrip("/")
        + get_settings().api_prefix
        + "/webhooks/whatsapp"
    )
    return await service.config_status(principal, connector_id, webhook_url)


@management_router.post("/test", response_model=WhatsAppTestResponse)
async def test_whatsapp_connector(
    payload: WhatsAppTestRequest,
    service: Annotated[WhatsAppService, Depends(get_whatsapp_service)],
    principal: Annotated[
        Principal,
        Depends(require_any_permission("connector.manage", "connector.secret_manage")),
    ],
) -> WhatsAppTestResponse:
    return await service.test_connection(principal, payload.connector_id)
