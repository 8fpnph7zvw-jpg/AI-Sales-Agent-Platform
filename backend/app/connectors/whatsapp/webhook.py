from __future__ import annotations

import hmac
import json
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import Principal, require_any_permission
from app.connectors.feishu.repository import FeishuConnectorRepository
from app.connectors.feishu.service import FeishuConnectorService
from app.connectors.whatsapp.repository import WhatsAppRepository
from app.connectors.whatsapp.schemas import (
    WhatsAppConfigStatusResponse,
    WhatsAppGatewayInboundRequest,
    WhatsAppGatewaySessionStatusRequest,
    WhatsAppSendRequest,
    WhatsAppSendResponse,
    WhatsAppTestRequest,
    WhatsAppTestResponse,
    WhatsAppWebhookResponse,
    WhatsAppWebSessionQrResponse,
    WhatsAppWebSessionStatusResponse,
)
from app.connectors.whatsapp.service import WhatsAppService
from app.core.config import get_settings
from app.core.encryption import ConfigCipher
from app.core.exceptions import AppError
from app.db.session import get_db
from app.integrations.dify.client import DifyClient
from app.modules.lead_score.repository import LeadScoreRepository
from app.services.dify_scoring_service import DifyScoringService
from app.services.lead_scoring_orchestrator import LeadScoringOrchestrator

webhook_router = APIRouter(prefix="/webhooks/whatsapp", tags=["WhatsApp Webhook"])
management_router = APIRouter(prefix="/connectors/whatsapp", tags=["WhatsApp Connector"])
send_router = APIRouter(prefix="/whatsapp", tags=["WhatsApp Connector"])
gateway_router = APIRouter(prefix="/conversations", tags=["WhatsApp Gateway"])


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
        LeadScoringOrchestrator(
            session,
            LeadScoreRepository(session),
            DifyScoringService(settings),
            FeishuConnectorService(
                session,
                FeishuConnectorRepository(session),
                ConfigCipher(settings),
                settings,
            ),
        ),
    )


@webhook_router.get("")
async def whatsapp_webhook_status() -> dict[str, str]:
    return {"status": "ok", "interface": "provider-adapter"}


@webhook_router.get("/{connector_id}")
async def verify_whatsapp_webhook(
    connector_id: str,
    service: Annotated[WhatsAppService, Depends(get_whatsapp_service)],
    mode: Annotated[str, Query(alias="hub.mode")],
    token: Annotated[str, Query(alias="hub.verify_token")],
    challenge: Annotated[str, Query(alias="hub.challenge")],
) -> Response:
    value = await service.verify_webhook(
        connector_id,
        mode=mode,
        token=token,
        challenge=challenge,
    )
    return Response(content=value, media_type="text/plain")


@webhook_router.post("/{connector_id}", response_model=WhatsAppWebhookResponse)
async def receive_whatsapp_webhook(
    connector_id: str,
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
        payload = json.loads(raw_body)
        if not isinstance(payload, dict):
            raise ValueError
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        raise AppError(
            422,
            "WHATSAPP_PAYLOAD_INVALID",
            "WhatsApp webhook payload is invalid.",
        ) from exc
    return await service.handle_webhook(
        connector_id,
        raw_body=raw_body,
        payload=payload,
        headers={key.lower(): value for key, value in request.headers.items()},
    )


@gateway_router.post("/message", response_model=WhatsAppWebhookResponse)
async def receive_whatsapp_gateway_message(
    payload: WhatsAppGatewayInboundRequest,
    request: Request,
    service: Annotated[WhatsAppService, Depends(get_whatsapp_service)],
) -> WhatsAppWebhookResponse:
    settings = get_settings()
    if not settings.whatsapp_gateway_token:
        raise AppError(
            503,
            "WHATSAPP_GATEWAY_NOT_CONFIGURED",
            "WHATSAPP_GATEWAY_TOKEN is not configured.",
        )
    supplied_token = request.headers.get("X-WhatsApp-Gateway-Token", "")
    if not hmac.compare_digest(supplied_token, settings.whatsapp_gateway_token):
        raise AppError(
            403,
            "WHATSAPP_GATEWAY_TOKEN_INVALID",
            "WhatsApp gateway authentication failed.",
        )
    raw_body = await request.body()
    if len(raw_body) > settings.whatsapp_webhook_max_bytes:
        raise AppError(
            413,
            "WHATSAPP_PAYLOAD_TOO_LARGE",
            "WhatsApp gateway payload exceeds the configured size limit.",
        )
    return await service.handle_gateway_message(
        payload,
        raw_body=raw_body,
        headers={key.lower(): value for key, value in request.headers.items()},
    )


@gateway_router.post(
    "/session-status",
    response_model=WhatsAppWebSessionStatusResponse,
)
async def receive_whatsapp_gateway_session_status(
    payload: WhatsAppGatewaySessionStatusRequest,
    request: Request,
    service: Annotated[WhatsAppService, Depends(get_whatsapp_service)],
) -> WhatsAppWebSessionStatusResponse:
    settings = get_settings()
    if not settings.whatsapp_gateway_token:
        raise AppError(
            503,
            "WHATSAPP_GATEWAY_NOT_CONFIGURED",
            "WHATSAPP_GATEWAY_TOKEN is not configured.",
        )
    supplied_token = request.headers.get("X-WhatsApp-Gateway-Token", "")
    if not hmac.compare_digest(supplied_token, settings.whatsapp_gateway_token):
        raise AppError(
            403,
            "WHATSAPP_GATEWAY_TOKEN_INVALID",
            "WhatsApp gateway authentication failed.",
        )
    return await service.handle_gateway_session_status(payload)


@send_router.post("/send", response_model=WhatsAppSendResponse)
async def send_whatsapp_message(
    payload: WhatsAppSendRequest,
    service: Annotated[WhatsAppService, Depends(get_whatsapp_service)],
    principal: Annotated[
        Principal,
        Depends(require_any_permission("message.send", "connector.manage")),
    ],
) -> WhatsAppSendResponse:
    return await service.send_message(principal, payload.recipient, payload.text)


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
        + f"/webhooks/whatsapp/{connector_id}"
    )
    return await service.config_status(principal, connector_id, webhook_url)


@management_router.post(
    "/{connector_id}/web-session/connect",
    response_model=WhatsAppWebSessionStatusResponse,
)
async def connect_whatsapp_web_session(
    connector_id: str,
    service: Annotated[WhatsAppService, Depends(get_whatsapp_service)],
    principal: Annotated[
        Principal,
        Depends(require_any_permission("connector.manage", "connector.secret_manage")),
    ],
) -> WhatsAppWebSessionStatusResponse:
    return await service.connect_web_session(principal, connector_id)


@management_router.get(
    "/{connector_id}/web-session/status",
    response_model=WhatsAppWebSessionStatusResponse,
)
async def whatsapp_web_session_status(
    connector_id: str,
    service: Annotated[WhatsAppService, Depends(get_whatsapp_service)],
    principal: Annotated[
        Principal,
        Depends(require_any_permission("connector.read", "connector.manage")),
    ],
) -> WhatsAppWebSessionStatusResponse:
    return await service.web_session_status(principal, connector_id)


@management_router.get(
    "/{connector_id}/web-session/qr",
    response_model=WhatsAppWebSessionQrResponse,
)
async def whatsapp_web_session_qr(
    connector_id: str,
    service: Annotated[WhatsAppService, Depends(get_whatsapp_service)],
    principal: Annotated[
        Principal,
        Depends(require_any_permission("connector.manage", "connector.secret_manage")),
    ],
) -> WhatsAppWebSessionQrResponse:
    return await service.web_session_qr(principal, connector_id)


@management_router.post(
    "/{connector_id}/web-session/reconnect",
    response_model=WhatsAppWebSessionStatusResponse,
)
async def reconnect_whatsapp_web_session(
    connector_id: str,
    service: Annotated[WhatsAppService, Depends(get_whatsapp_service)],
    principal: Annotated[
        Principal,
        Depends(require_any_permission("connector.manage", "connector.secret_manage")),
    ],
) -> WhatsAppWebSessionStatusResponse:
    return await service.reconnect_web_session(principal, connector_id)


@management_router.delete(
    "/{connector_id}/web-session",
    response_model=WhatsAppWebSessionStatusResponse,
)
async def disconnect_whatsapp_web_session(
    connector_id: str,
    service: Annotated[WhatsAppService, Depends(get_whatsapp_service)],
    principal: Annotated[
        Principal,
        Depends(require_any_permission("connector.manage", "connector.secret_manage")),
    ],
) -> WhatsAppWebSessionStatusResponse:
    return await service.disconnect_web_session(principal, connector_id)


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
