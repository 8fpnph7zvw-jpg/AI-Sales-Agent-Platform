from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.api.dependencies.auth import Principal
from app.connectors.whatsapp.providers.webjs_gateway import WhatsAppWebJsGatewayAdapter
from app.connectors.whatsapp.schemas import (
    WhatsAppGatewayInboundRequest,
    WhatsAppGatewaySessionStatusRequest,
)
from app.connectors.whatsapp.service import WhatsAppService
from app.core.config import Settings
from app.integrations.dify.client import DifyChatResult
from app.models.connector.webhook_log import WebhookLog
from app.models.connector.whatsapp_session import WhatsAppSession
from app.models.conversation.conversation import Conversation
from app.models.conversation.message import Message


class FlowCipher:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values

    def decrypt(self, encrypted: bytes, *, associated_data: str) -> str:
        del encrypted
        return self.values[associated_data.rsplit(":", 1)[-1]]


class FlowSession:
    def __init__(self, repository: FlowRepository) -> None:
        self.repository = repository
        self.models: list[Any] = []
        self.next_id = 100
        self.commit_count = 0

    def add(self, model: Any) -> None:
        self.next_id += 1
        if getattr(model, "id", None) is None:
            model.id = self.next_id
        if hasattr(type(model), "public_id") and getattr(model, "public_id", None) is None:
            model.public_id = f"test-public-{self.next_id}"
        if isinstance(model, WhatsAppSession):
            self.repository.whatsapp_session = model
        elif isinstance(model, WebhookLog):
            model.attempt_count = model.attempt_count or 0
            self.repository.webhook_log = model
        elif isinstance(model, Conversation):
            model.unread_count = model.unread_count or 0
            model.version = model.version or 1
            self.repository.conversation = model
        elif isinstance(model, Message):
            self.repository.messages.append(model)
        self.models.append(model)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.commit_count += 1


class FlowRepository:
    def __init__(self, connector: SimpleNamespace, tenant: SimpleNamespace) -> None:
        self.connector = connector
        self.tenant = tenant
        self.whatsapp_session: WhatsAppSession | None = None
        self.webhook_log: WebhookLog | None = None
        self.conversation: Conversation | None = None
        self.messages: list[Message] = []
        self.sequence = 0
        self.configs = [
            SimpleNamespace(
                config_key="adapter",
                value_encrypted=b"adapter",
                secret_ref=None,
            ),
            SimpleNamespace(
                config_key="session_id",
                value_encrypted=b"session_id",
                secret_ref=None,
            ),
        ]

    async def get_connector_context(
        self,
        tenant_id: int,
        public_id: str,
        *,
        for_update: bool = False,
    ) -> tuple[SimpleNamespace, SimpleNamespace] | None:
        del for_update
        if tenant_id == self.tenant.id and public_id == self.connector.public_id:
            return self.connector, self.tenant
        return None

    async def get_connector_by_session(
        self,
        session_id: str,
    ) -> tuple[SimpleNamespace, SimpleNamespace] | None:
        if (
            self.whatsapp_session is not None
            and self.whatsapp_session.session_id == session_id
        ):
            return self.connector, self.tenant
        return None

    async def get_configs(self, connector_id: int) -> list[SimpleNamespace]:
        assert connector_id == self.connector.id
        return self.configs

    async def get_session_claim(self, **kwargs: Any) -> None:
        assert kwargs["exclude_connector_id"] == self.connector.id
        return None

    async def get_whatsapp_session(
        self,
        tenant_id: int,
        connector_id: int,
        *,
        for_update: bool = False,
    ) -> WhatsAppSession | None:
        del for_update
        assert tenant_id == self.tenant.id
        assert connector_id == self.connector.id
        return self.whatsapp_session

    def add_whatsapp_session(self, whatsapp_session: WhatsAppSession) -> None:
        self.whatsapp_session = whatsapp_session

    async def get_webhook_log(
        self,
        connector_id: int,
        provider_event_id: str,
    ) -> WebhookLog | None:
        del connector_id, provider_event_id
        return self.webhook_log

    async def get_message_context(self, tenant_id: int, idempotency_key: str) -> None:
        del tenant_id, idempotency_key
        return None

    async def get_latest_run(self, trigger_message_id: int) -> None:
        del trigger_message_id
        return None

    async def get_customer_context(
        self,
        tenant_id: int,
        connector_id: int,
        external_contact_id: str,
    ) -> None:
        del tenant_id, connector_id, external_contact_id
        return None

    async def get_customer_by_phone(self, tenant_id: int, phone_e164: str) -> None:
        del tenant_id, phone_e164
        return None

    async def get_open_conversation(
        self,
        tenant_id: int,
        customer_session_id: int,
    ) -> None:
        del tenant_id, customer_session_id
        return None

    async def get_conversation_for_update(self, conversation_id: int) -> Conversation | None:
        if self.conversation is not None and self.conversation.id == conversation_id:
            return self.conversation
        return None

    async def next_sequence(self, conversation_id: int) -> int:
        del conversation_id
        self.sequence += 1
        return self.sequence

    async def get_message(self, message_id: int) -> Message | None:
        return next((message for message in self.messages if message.id == message_id), None)


class FlowDify:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def chat(self, **kwargs: Any) -> DifyChatResult:
        self.queries.append(kwargs["query"])
        return DifyChatResult(
            answer="Dify sales reply",
            conversation_id="dify-conversation-1",
            task_id="dify-task-1",
            message_id="dify-message-1",
            retry_count=0,
        )


@pytest.mark.asyncio
async def test_whatsapp_web_qr_connected_inbound_dify_and_outbound_flow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connector = SimpleNamespace(
        id=10,
        public_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
        tenant_id=1,
        provider="whatsapp",
        status="draft",
        session_id="sales-web-01",
        phone=None,
        external_account_id="sales-web-01",
        health_status=None,
        health_detail=None,
        last_health_check_at=None,
        last_connected_at=None,
        last_disconnect_reason=None,
    )
    tenant = SimpleNamespace(
        id=1,
        public_id="01ARZ3NDEKTSV4RRFFQ69G5FAW",
    )
    repository = FlowRepository(connector, tenant)
    session = FlowSession(repository)
    dify = FlowDify()
    gateway_requests: list[tuple[str, str, dict[str, Any]]] = []

    async def fake_gateway_request(
        _adapter: WhatsAppWebJsGatewayAdapter,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        gateway_requests.append((method, path, kwargs))
        if path.endswith("/connect"):
            return {
                "sessionId": "sales-web-01",
                "status": "WAITING_QR",
                "phone": None,
                "lastError": None,
            }
        if path.endswith("/qr"):
            return {
                "sessionId": "sales-web-01",
                "status": "WAITING_QR",
                "phone": None,
                "lastError": None,
                "qr": "qr-token",
                "dataUrl": "data:image/png;base64,qr-code",
            }
        if path.endswith("/status"):
            return {
                "sessionId": "sales-web-01",
                "status": "CONNECTED",
                "phone": "15550001111",
                "lastError": None,
            }
        if path.endswith("/send"):
            assert kwargs["json"] == {
                "phone": "15550002222",
                "message": "Dify sales reply",
                "sessionId": "sales-web-01",
            }
            return {"messageId": "webjs-outbound-1", "status": "SENT"}
        raise AssertionError(f"Unexpected gateway request: {method} {path}")

    monkeypatch.setattr(WhatsAppWebJsGatewayAdapter, "_request", fake_gateway_request)
    settings = Settings(
        _env_file=None,
        whatsapp_gateway_url="http://whatsapp-connector:3001",
        whatsapp_gateway_token="gateway-secret",
    )
    service = WhatsAppService(
        session,
        repository,
        settings,
        FlowCipher({"adapter": "webjs_gateway", "session_id": "sales-web-01"}),
        dify,
    )
    principal = Principal(
        user_id=20,
        user_public_id="user-public-id",
        tenant_id=1,
        tenant_public_id=tenant.public_id,
        permissions=frozenset({"connector.manage", "connector.secret_manage"}),
    )

    connecting = await service.connect_web_session(principal, connector.public_id)
    assert connecting.status == "WAITING_QR"

    qr = await service.web_session_qr(principal, connector.public_id)
    assert qr.data_url == "data:image/png;base64,qr-code"
    assert repository.whatsapp_session is not None
    assert repository.whatsapp_session.status == "waiting_qr"

    connected = await service.handle_gateway_session_status(
        WhatsAppGatewaySessionStatusRequest(
            session_id="sales-web-01",
            status="CONNECTED",
            phone="15550001111",
        )
    )
    assert connected.status == "CONNECTED"
    assert connector.status == "active"
    assert connector.phone == "15550001111"
    assert repository.whatsapp_session.status == "connected"
    assert repository.whatsapp_session.phone == "15550001111"
    assert repository.whatsapp_session.qr_code is None

    response = await service.handle_gateway_message(
        WhatsAppGatewayInboundRequest(
            phone="15550002222",
            message="Need a quotation",
            message_id="webjs-inbound-1",
            timestamp=1785376800,
            session_id="sales-web-01",
        ),
        raw_body=b'{"message":"Need a quotation"}',
        headers={"x-whatsapp-gateway-token": "gateway-secret"},
    )

    assert response.processed == 1
    assert dify.queries == ["Need a quotation"]
    outbound = next(message for message in repository.messages if message.direction == "outbound")
    assert outbound.status == "sent"
    assert outbound.external_message_id == "webjs-outbound-1"
    assert repository.webhook_log is not None
    assert repository.webhook_log.status == "processed"
    assert [path for _, path, _ in gateway_requests] == [
        "/api/whatsapp/connect",
        "/api/whatsapp/qr",
        "/api/whatsapp/send",
    ]
