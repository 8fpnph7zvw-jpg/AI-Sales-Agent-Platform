from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.api.dependencies.auth import Principal
from app.connectors.whatsapp.schemas import WhatsAppSendResponse
from app.core.config import Settings
from app.modules.conversation.schemas import ConversationMessageCreate
from app.modules.conversation.service import ConversationService


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0
        self.added: list[Any] = []

    def add(self, value: Any) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1


class FakeRepository:
    def __init__(self) -> None:
        self.conversation = SimpleNamespace(
            id=20,
            public_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
            status="open",
            customer_session_id=30,
            last_message_at=None,
            version=1,
        )
        self.customer_session = SimpleNamespace(
            external_contact_id="8613800138000@c.us",
        )
        self.connector = SimpleNamespace(id=40, provider="whatsapp")
        self.whatsapp_session = SimpleNamespace(
            session_id="6bba5383-bf1f-42ce-945f-c5f8920150b8",
            session_name="tenant-sales",
        )
        self.message: Any = None

    async def get_by_public_id_for_update(
        self,
        tenant_id: int,
        public_id: str,
    ) -> Any:
        assert tenant_id == 1
        assert public_id == self.conversation.public_id
        return self.conversation

    async def get_message_by_idempotency(
        self,
        tenant_id: int,
        idempotency_key: str,
    ) -> None:
        del tenant_id, idempotency_key
        return None

    async def get_delivery_context(
        self,
        tenant_id: int,
        customer_session_id: int,
    ) -> tuple[Any, Any, Any]:
        assert tenant_id == 1
        assert customer_session_id == 30
        return self.customer_session, self.connector, self.whatsapp_session

    async def get_connector_id(self, customer_session_id: int) -> int:
        assert customer_session_id == 30
        return self.connector.id

    async def next_sequence(self, conversation_id: int) -> int:
        assert conversation_id == 20
        return 1

    def add_message(self, message: Any) -> None:
        message.id = 50
        message.public_id = "01ARZ3NDEKTSV4RRFFQ69G5FB0"
        self.message = message


@pytest.mark.asyncio
async def test_admin_reply_to_real_whatsapp_conversation_is_sent_immediately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: dict[str, str] = {}

    async def fake_send_text(_client: Any, recipient: str, text: str) -> WhatsAppSendResponse:
        sent.update(recipient=recipient, text=text)
        return WhatsAppSendResponse.model_validate(
            {"messageId": "wamid.admin-reply"}
        )

    monkeypatch.setattr(
        "app.modules.conversation.service.OpenWAClient.send_text",
        fake_send_text,
    )
    session = FakeSession()
    repository = FakeRepository()
    service = ConversationService(
        session,  # type: ignore[arg-type]
        repository,  # type: ignore[arg-type]
        Settings(_env_file=None, openwa_api_key="openwa-key"),
    )
    principal = Principal(
        user_id=10,
        user_public_id="01ARZ3NDEKTSV4RRFFQ69G5FB1",
        tenant_id=1,
        tenant_public_id="01ARZ3NDEKTSV4RRFFQ69G5FB2",
        permissions=frozenset({"message.send"}),
    )

    response = await service.send_message(
        principal,
        ConversationMessageCreate(
            conversation_id=repository.conversation.public_id,
            content="您好，这是人工回复",
            idempotency_key="admin-send-001",
        ),
    )

    assert sent == {
        "recipient": "8613800138000@c.us",
        "text": "您好，这是人工回复",
    }
    assert response.status == "sent"
    assert response.source == "web"
    assert repository.message.external_message_id == "wamid.admin-reply"
    assert session.added == []
