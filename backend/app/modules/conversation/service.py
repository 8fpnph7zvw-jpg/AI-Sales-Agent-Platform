from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import Principal
from app.connectors.whatsapp.client import OpenWAClient
from app.core.config import Settings
from app.core.exceptions import ConflictError, ResourceNotFoundError
from app.models.conversation.conversation import Conversation
from app.models.conversation.message import Message
from app.models.customer.customer_session import CustomerSession
from app.models.system.outbox_event import OutboxEvent
from app.modules.conversation.repository import ConversationRepository
from app.modules.conversation.schemas import (
    ConversationCreate,
    ConversationListResponse,
    ConversationMessageCreate,
    ConversationMessageListResponse,
    ConversationMessageResponse,
    ConversationRead,
)


class ConversationService:
    def __init__(
        self,
        session: AsyncSession,
        repository: ConversationRepository,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.repository = repository
        self.settings = settings

    async def create(
        self,
        principal: Principal,
        payload: ConversationCreate,
    ) -> ConversationRead:
        customer = await self.repository.get_customer(
            principal.tenant_id,
            payload.customer_id,
        )
        if customer is None:
            raise ResourceNotFoundError("Customer")
        connector = await self.repository.get_demo_connector(principal.tenant_id)
        if connector is None:
            raise ConflictError(
                "DEMO_CONNECTOR_REQUIRED",
                "Run scripts/initialize_demo.py before creating an Agent conversation.",
            )

        now = datetime.now(UTC)
        customer_session = await self.repository.get_agent_console_session(
            principal.tenant_id,
            customer.id,
            connector.id,
        )
        if customer_session is None:
            customer_session = CustomerSession(
                tenant_id=principal.tenant_id,
                customer_id=customer.id,
                connector_id=connector.id,
                external_contact_id=f"demo:{customer.public_id}",
                external_thread_id="agent-console",
                status="active",
                first_seen_at=now,
                last_seen_at=now,
                metadata_json={"source": "agent_console"},
            )
            self.repository.add(customer_session)
            await self.session.flush()
        else:
            customer_session.last_seen_at = now

        conversation = Conversation(
            tenant_id=principal.tenant_id,
            customer_id=customer.id,
            customer_session_id=customer_session.id,
            subject=payload.subject or f"Agent conversation - {customer.name}",
            status="open",
            mode="ai",
            assigned_user_id=principal.user_id,
            ai_enabled=True,
        )
        self.repository.add(conversation)
        await self.session.commit()
        await self.session.refresh(conversation)
        return ConversationRead(
            id=conversation.public_id,
            customer_id=customer.public_id,
            customer_name=customer.name,
            channel=connector.provider,
            status=conversation.status,
            ai_status="enabled",
            last_message_preview=None,
            last_message_at=conversation.last_message_at,
            unread_count=conversation.unread_count,
            created_at=conversation.created_at,
        )

    async def list(
        self,
        principal: Principal,
        *,
        limit: int,
        offset: int,
        status: str | None,
        search: str | None,
    ) -> ConversationListResponse:
        assigned_user_id = (
            None
            if principal.permissions.intersection(
                {"conversation.read_all", "conversation.read_team"}
            )
            else principal.user_id
        )
        rows, total = await self.repository.list(
            principal.tenant_id,
            limit=limit,
            offset=offset,
            status=status,
            search=search,
            assigned_user_id=assigned_user_id,
        )
        return ConversationListResponse(
            data=[
                ConversationRead(
                    id=conversation.public_id,
                    customer_id=customer.public_id,
                    customer_name=customer.name,
                    channel=connector.provider,
                    status=conversation.status,
                    ai_status="enabled" if conversation.ai_enabled else "disabled",
                    last_message_preview=preview,
                    last_message_at=conversation.last_message_at,
                    unread_count=conversation.unread_count,
                    created_at=conversation.created_at,
                )
                for conversation, customer, connector, preview in rows
            ],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def list_messages(
        self,
        principal: Principal,
        conversation_id: str,
        *,
        limit: int,
        before_sequence: int | None,
    ) -> ConversationMessageListResponse:
        messages, total = await self.repository.list_messages(
            principal.tenant_id,
            conversation_id,
            limit=limit,
            before_sequence=before_sequence,
        )
        if total < 0:
            raise ResourceNotFoundError("Conversation")
        return ConversationMessageListResponse(
            data=[
                self._response(message, conversation_id)
                for message in messages
            ],
            total=total,
            limit=limit,
            offset=0,
        )

    async def send_message(
        self,
        principal: Principal,
        payload: ConversationMessageCreate,
    ) -> ConversationMessageResponse:
        conversation = await self.repository.get_by_public_id_for_update(
            principal.tenant_id,
            payload.conversation_id,
        )
        if conversation is None:
            raise ResourceNotFoundError("Conversation")
        if conversation.status in {"closed", "blocked"}:
            raise ConflictError(
                "CONVERSATION_NOT_WRITABLE",
                "Messages cannot be sent to a closed or blocked conversation.",
            )

        # Re-check after obtaining the conversation lock.
        existing = await self.repository.get_message_by_idempotency(
            principal.tenant_id,
            payload.idempotency_key,
        )
        if existing is not None:
            if existing.conversation_id != conversation.id:
                raise ConflictError(
                    "IDEMPOTENCY_KEY_REUSED",
                    "Idempotency key was already used for another conversation.",
                )
            return self._response(existing, payload.conversation_id, duplicate=True)

        delivery_context = await self.repository.get_delivery_context(
            principal.tenant_id,
            conversation.customer_session_id,
        )
        now = datetime.now(UTC)
        message = Message(
            tenant_id=principal.tenant_id,
            conversation_id=conversation.id,
            connector_id=await self.repository.get_connector_id(conversation.customer_session_id),
            sequence_no=await self.repository.next_sequence(conversation.id),
            direction="outbound",
            sender_type="user",
            sender_ref=principal.user_public_id,
            source="web",
            message_type=payload.message_type,
            content_text=payload.content,
            content_json=payload.content_json,
            idempotency_key=payload.idempotency_key,
            status="queued",
            created_at=now,
        )
        self.repository.add_message(message)
        await self.session.flush()

        conversation.last_message_at = now
        conversation.version += 1
        is_live_whatsapp = bool(
            delivery_context
            and delivery_context[1].provider == "whatsapp"
            and delivery_context[2] is not None
            and not delivery_context[0].external_contact_id.startswith("demo:")
        )
        if not is_live_whatsapp:
            self.session.add(
                OutboxEvent(
                    tenant_id=principal.tenant_id,
                    aggregate_type="conversation",
                    aggregate_id=conversation.public_id,
                    event_type="connector.message.send.requested.v1",
                    payload={
                        "message_id": message.public_id,
                        "conversation_id": conversation.public_id,
                    },
                    available_at=now,
                )
            )
        await self.session.commit()
        if is_live_whatsapp:
            customer_session, _connector, whatsapp_session = delivery_context
            if self.settings is None or whatsapp_session is None:
                raise ConflictError(
                    "WHATSAPP_DELIVERY_NOT_CONFIGURED",
                    "WhatsApp delivery is not configured for this conversation.",
                )
            client = OpenWAClient(
                self.settings,
                session_id=whatsapp_session.session_id,
                session_name=whatsapp_session.session_name,
            )
            try:
                result = await client.send_text(
                    customer_session.external_contact_id,
                    payload.content,
                )
            except Exception as exc:
                message.status = "failed"
                message.error_code = getattr(exc, "code", "WHATSAPP_SEND_FAILED")
                message.content_json = {
                    **(message.content_json or {}),
                    "send_error": str(exc)[:1000],
                }
                await self.session.commit()
                raise
            message.status = "sent"
            message.external_message_id = result.message_id
            message.sent_at = datetime.now(UTC)
            await self.session.commit()
        return self._response(message, conversation.public_id)

    @staticmethod
    def _response(
        message: Message,
        conversation_public_id: str,
        *,
        duplicate: bool = False,
    ) -> ConversationMessageResponse:
        return ConversationMessageResponse(
            id=message.public_id,
            conversation_id=conversation_public_id,
            sequence_no=message.sequence_no,
            direction=message.direction,
            sender_type=message.sender_type,
            source=message.source,
            message_type=message.message_type,
            content=message.content_text or "",
            status=message.status,
            duplicate=duplicate,
            created_at=message.created_at,
        )
