from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai.ai_agent_run import AiAgentRun
from app.models.conversation.conversation import Conversation
from app.models.conversation.message import Message
from app.models.customer.customer import Customer
from app.models.customer.customer_session import CustomerSession


class AiAgentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_conversation_for_update(
        self,
        tenant_id: int,
        public_id: str,
    ) -> tuple[Conversation, str, int] | None:
        statement = (
            select(Conversation, Customer.public_id, CustomerSession.connector_id)
            .join(Customer, Customer.id == Conversation.customer_id)
            .join(CustomerSession, CustomerSession.id == Conversation.customer_session_id)
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.public_id == public_id,
            )
            .with_for_update()
        )
        row = (await self.session.execute(statement)).one_or_none()
        return (row[0], row[1], row[2]) if row else None

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

    async def get_run_by_trigger_message(self, trigger_message_id: int) -> AiAgentRun | None:
        statement = select(AiAgentRun).where(AiAgentRun.trigger_message_id == trigger_message_id)
        return await self.session.scalar(statement)

    async def get_message(self, message_id: int) -> Message | None:
        return await self.session.get(Message, message_id)

    async def latest_dify_conversation_id(self, conversation_id: int) -> str | None:
        statement = (
            select(AiAgentRun.dify_conversation_id)
            .where(
                AiAgentRun.conversation_id == conversation_id,
                AiAgentRun.status == "succeeded",
                AiAgentRun.dify_conversation_id.is_not(None),
            )
            .order_by(AiAgentRun.id.desc())
            .limit(1)
        )
        return await self.session.scalar(statement)

    async def next_sequence(self, conversation_id: int) -> int:
        statement = select(func.coalesce(func.max(Message.sequence_no), 0) + 1).where(
            Message.conversation_id == conversation_id
        )
        return int((await self.session.scalar(statement)) or 1)

    def add(self, entity: Message | AiAgentRun) -> None:
        self.session.add(entity)
