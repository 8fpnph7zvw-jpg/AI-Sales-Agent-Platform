from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.connector.connector import Connector
from app.models.connector.connector_config import ConnectorConfig
from app.models.connector.whatsapp_session import WhatsAppSession
from app.models.conversation.conversation import Conversation
from app.models.conversation.message import Message
from app.models.customer.customer import Customer
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

    async def get_customer(self, tenant_id: int, public_id: str) -> Customer | None:
        return await self.session.scalar(
            select(Customer).where(
                Customer.tenant_id == tenant_id,
                Customer.public_id == public_id,
                Customer.deleted_at.is_(None),
            )
        )

    async def get_demo_connector(self, tenant_id: int) -> Connector | None:
        statement = (
            select(Connector)
            .where(
                Connector.tenant_id == tenant_id,
                Connector.deleted_at.is_(None),
                Connector.provider == "whatsapp",
                Connector.external_account_id == "demo-template",
            )
            .limit(1)
        )
        return await self.session.scalar(statement)

    async def get_agent_console_session(
        self,
        tenant_id: int,
        customer_id: int,
        connector_id: int,
    ) -> CustomerSession | None:
        statement = select(CustomerSession).where(
            CustomerSession.tenant_id == tenant_id,
            CustomerSession.customer_id == customer_id,
            CustomerSession.connector_id == connector_id,
            CustomerSession.external_thread_id == "agent-console",
        )
        return await self.session.scalar(statement)

    async def list(
        self,
        tenant_id: int,
        *,
        limit: int,
        offset: int,
        status: str | None,
        search: str | None,
        assigned_user_id: int | None,
    ) -> tuple[list[tuple[Conversation, Customer, Connector, str | None]], int]:
        latest_message = (
            select(Message.content_text)
            .where(Message.conversation_id == Conversation.id)
            .order_by(Message.sequence_no.desc())
            .limit(1)
            .scalar_subquery()
        )
        filters = [Conversation.tenant_id == tenant_id]
        if status:
            filters.append(Conversation.status == status)
        if assigned_user_id is not None:
            filters.append(Conversation.assigned_user_id == assigned_user_id)
        if search:
            pattern = f"%{search.strip()}%"
            filters.append(
                or_(
                    Customer.name.like(pattern),
                    Customer.company_name.like(pattern),
                    Conversation.subject.like(pattern),
                )
            )
        base = (
            select(Conversation, Customer, Connector, latest_message)
            .join(Customer, Customer.id == Conversation.customer_id)
            .join(CustomerSession, CustomerSession.id == Conversation.customer_session_id)
            .join(Connector, Connector.id == CustomerSession.connector_id)
            .where(*filters)
        )
        rows = list(
            (
                await self.session.execute(
                    base.order_by(
                        Conversation.last_message_at.desc(),
                        Conversation.created_at.desc(),
                    )
                    .limit(limit)
                    .offset(offset)
                )
            ).tuples()
        )
        total = int(
            (
                await self.session.scalar(
                    select(func.count(Conversation.id))
                    .join(Customer, Customer.id == Conversation.customer_id)
                    .where(*filters)
                )
            )
            or 0
        )
        return rows, total

    async def list_messages(
        self,
        tenant_id: int,
        conversation_public_id: str,
        *,
        limit: int,
        before_sequence: int | None,
    ) -> tuple[list[Message], int]:
        conversation_id = await self.session.scalar(
            select(Conversation.id).where(
                Conversation.tenant_id == tenant_id,
                Conversation.public_id == conversation_public_id,
            )
        )
        if conversation_id is None:
            return [], -1
        filters = [Message.conversation_id == conversation_id]
        if before_sequence is not None:
            filters.append(Message.sequence_no < before_sequence)
        rows = list(
            (
                await self.session.scalars(
                    select(Message)
                    .where(*filters)
                    .order_by(Message.sequence_no)
                    .limit(limit)
                )
            ).all()
        )
        total = int(
            (await self.session.scalar(select(func.count(Message.id)).where(*filters))) or 0
        )
        return rows, total

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

    async def get_delivery_context(
        self,
        tenant_id: int,
        customer_session_id: int,
    ) -> tuple[CustomerSession, Connector, WhatsAppSession | None] | None:
        row = (
            await self.session.execute(
                select(CustomerSession, Connector, WhatsAppSession)
                .join(Connector, Connector.id == CustomerSession.connector_id)
                .outerjoin(
                    WhatsAppSession,
                    WhatsAppSession.connector_id == Connector.id,
                )
                .where(
                    CustomerSession.id == customer_session_id,
                    CustomerSession.tenant_id == tenant_id,
                    Connector.tenant_id == tenant_id,
                    Connector.deleted_at.is_(None),
                )
                .limit(1)
            )
        ).one_or_none()
        return (row[0], row[1], row[2]) if row else None

    async def get_connector_configs(self, connector_id: int) -> list[ConnectorConfig]:
        return list(
            (
                await self.session.scalars(
                    select(ConnectorConfig).where(
                        ConnectorConfig.connector_id == connector_id,
                        ConnectorConfig.value_encrypted.is_not(None),
                    )
                )
            ).all()
        )

    def add_message(self, message: Message) -> None:
        self.session.add(message)

    def add(self, model: Conversation | CustomerSession) -> None:
        self.session.add(model)
