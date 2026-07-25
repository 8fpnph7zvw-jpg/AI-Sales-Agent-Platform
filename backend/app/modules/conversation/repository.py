from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation.conversation import Conversation
from app.models.conversation.message import Message
from app.models.customer.customer_session import CustomerSession


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_public_id_for_update(
        self,
        tenant_id: int,
        public_id: str,
    ) -> Conversation | None:
        statement = (
            select(Conversation)
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.public_id == public_id,
            )
            .with_for_update()
        )
        return await self.session.scalar(statement)

    async def get_message_by_idempotency(
        self,
        tenant_id: int,
        idempotency_key: str,
    ) -> Message | None:
        statement = select(Message).where(
            Message.tenant_id == tenant_id,
            Message.idempotency_key == idempotency_key,
        )
        return await self.session.scalar(statement)

    async def next_sequence(self, conversation_id: int) -> int:
        statement = select(func.coalesce(func.max(Message.sequence_no), 0) + 1).where(
            Message.conversation_id == conversation_id
        )
        return int((await self.session.scalar(statement)) or 1)

    async def get_connector_id(self, customer_session_id: int) -> int:
        statement = select(CustomerSession.connector_id).where(
            CustomerSession.id == customer_session_id
        )
        connector_id = await self.session.scalar(statement)
        if connector_id is None:
            raise RuntimeError("Conversation customer session has no connector.")
        return int(connector_id)

    def add_message(self, message: Message) -> None:
        self.session.add(message)
