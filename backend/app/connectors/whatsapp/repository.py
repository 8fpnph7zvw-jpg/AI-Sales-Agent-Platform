from __future__ import annotations

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai.ai_agent_run import AiAgentRun
from app.models.auth.tenant import Tenant
from app.models.connector.connector import Connector
from app.models.connector.connector_config import ConnectorConfig
from app.models.connector.webhook_log import WebhookLog
from app.models.connector.whatsapp_session import WhatsAppSession
from app.models.conversation.conversation import Conversation
from app.models.conversation.message import Message
from app.models.customer.customer import Customer
from app.models.customer.customer_session import CustomerSession


class WhatsAppRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_connector_by_session(
        self,
        session_id: str,
    ) -> tuple[Connector, Tenant] | None:
        row = (
            await self.session.execute(
                select(Connector, Tenant)
                .join(Tenant, Tenant.id == Connector.tenant_id)
                .join(
                    WhatsAppSession,
                    WhatsAppSession.connector_id == Connector.id,
                )
                .where(
                    Connector.provider == "whatsapp",
                    or_(
                        WhatsAppSession.session_id == session_id,
                        WhatsAppSession.session_name == session_id,
                    ),
                    Connector.status == "active",
                    Connector.deleted_at.is_(None),
                    Tenant.status == "active",
                    Tenant.deleted_at.is_(None),
                )
                .limit(1)
                .with_for_update()
            )
        ).one_or_none()
        return (row[0], row[1]) if row else None

    async def get_management_context(
        self,
        tenant_id: int,
        *,
        for_update: bool = False,
    ) -> tuple[Connector, Tenant] | None:
        statement = (
            select(Connector, Tenant)
            .join(Tenant, Tenant.id == Connector.tenant_id)
            .where(
                Connector.tenant_id == tenant_id,
                Connector.provider == "whatsapp",
                Connector.deleted_at.is_(None),
                Tenant.status == "active",
                Tenant.deleted_at.is_(None),
            )
            .order_by(
                case(
                    (Connector.status == "active", 0),
                    (Connector.status == "draft", 1),
                    else_=2,
                ),
                Connector.id,
            )
            .limit(1)
        )
        if for_update:
            statement = statement.with_for_update()
        row = (await self.session.execute(statement)).one_or_none()
        return (row[0], row[1]) if row else None

    async def get_whatsapp_session(
        self,
        tenant_id: int,
        connector_id: int,
        *,
        for_update: bool = False,
    ) -> WhatsAppSession | None:
        statement = select(WhatsAppSession).where(
            WhatsAppSession.tenant_id == tenant_id,
            WhatsAppSession.connector_id == connector_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    def add_whatsapp_session(self, whatsapp_session: WhatsAppSession) -> None:
        self.session.add(whatsapp_session)

    async def get_session_claim(
        self,
        *,
        session_name: str,
        session_id: str | None = None,
        exclude_connector_id: int | None = None,
    ) -> WhatsAppSession | None:
        identities = [WhatsAppSession.session_name == session_name]
        if session_id:
            identities.append(WhatsAppSession.session_id == session_id)
        statement = select(WhatsAppSession).where(or_(*identities))
        if exclude_connector_id is not None:
            statement = statement.where(
                WhatsAppSession.connector_id != exclude_connector_id
            )
        return await self.session.scalar(statement.limit(1))

    async def get_connector_for_update(
        self,
        tenant_id: int,
        public_id: str,
    ) -> Connector | None:
        return await self.session.scalar(
            select(Connector)
            .where(
                Connector.tenant_id == tenant_id,
                Connector.public_id == public_id,
                Connector.provider == "whatsapp",
                Connector.deleted_at.is_(None),
            )
            .with_for_update()
        )

    async def get_configs(self, connector_id: int) -> list[ConnectorConfig]:
        return list(
            (
                await self.session.scalars(
                    select(ConnectorConfig).where(
                        ConnectorConfig.connector_id == connector_id
                    )
                )
            ).all()
        )

    async def verification_candidates(
        self,
    ) -> list[tuple[Connector, ConnectorConfig]]:
        return list(
            (
                await self.session.execute(
                    select(Connector, ConnectorConfig)
                    .join(
                        ConnectorConfig,
                        ConnectorConfig.connector_id == Connector.id,
                    )
                    .where(
                        Connector.provider == "whatsapp",
                        Connector.status.in_(("draft", "active")),
                        Connector.deleted_at.is_(None),
                        ConnectorConfig.config_key == "verify_token",
                    )
                )
            ).tuples()
        )

    async def get_webhook_log(
        self,
        connector_id: int,
        provider_event_id: str,
    ) -> WebhookLog | None:
        return await self.session.scalar(
            select(WebhookLog).where(
                WebhookLog.connector_id == connector_id,
                WebhookLog.provider_event_id == provider_event_id,
            )
        )

    async def get_customer_context(
        self,
        tenant_id: int,
        connector_id: int,
        external_contact_id: str,
    ) -> tuple[CustomerSession, Customer] | None:
        row = (
            await self.session.execute(
                select(CustomerSession, Customer)
                .join(Customer, Customer.id == CustomerSession.customer_id)
                .where(
                    CustomerSession.tenant_id == tenant_id,
                    CustomerSession.connector_id == connector_id,
                    CustomerSession.external_contact_id == external_contact_id,
                    CustomerSession.external_thread_id == "",
                )
                .limit(1)
            )
        ).one_or_none()
        return (row[0], row[1]) if row else None

    async def get_customer_by_phone(
        self,
        tenant_id: int,
        phone_e164: str,
    ) -> Customer | None:
        return await self.session.scalar(
            select(Customer).where(
                Customer.tenant_id == tenant_id,
                Customer.phone_e164 == phone_e164,
                Customer.deleted_at.is_(None),
            )
        )

    async def get_open_conversation(
        self,
        tenant_id: int,
        customer_session_id: int,
    ) -> Conversation | None:
        return await self.session.scalar(
            select(Conversation)
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.customer_session_id == customer_session_id,
                Conversation.status.in_(("open", "pending")),
            )
            .order_by(Conversation.id.desc())
            .limit(1)
            .with_for_update()
        )

    async def get_conversation_for_update(
        self,
        conversation_id: int,
    ) -> Conversation | None:
        return await self.session.scalar(
            select(Conversation)
            .where(Conversation.id == conversation_id)
            .with_for_update()
        )

    async def get_message_context(
        self,
        tenant_id: int,
        idempotency_key: str,
    ) -> tuple[Message, Conversation, CustomerSession, Customer] | None:
        row = (
            await self.session.execute(
                select(Message, Conversation, CustomerSession, Customer)
                .join(Conversation, Conversation.id == Message.conversation_id)
                .join(
                    CustomerSession,
                    CustomerSession.id == Conversation.customer_session_id,
                )
                .join(Customer, Customer.id == Conversation.customer_id)
                .where(
                    Message.tenant_id == tenant_id,
                    Message.idempotency_key == idempotency_key,
                )
                .limit(1)
            )
        ).one_or_none()
        return (row[0], row[1], row[2], row[3]) if row else None

    async def get_latest_run(self, trigger_message_id: int) -> AiAgentRun | None:
        return await self.session.scalar(
            select(AiAgentRun)
            .where(AiAgentRun.trigger_message_id == trigger_message_id)
            .order_by(AiAgentRun.id.desc())
            .limit(1)
        )

    async def get_message(self, message_id: int) -> Message | None:
        return await self.session.get(Message, message_id)

    async def latest_dify_conversation_id(self, conversation_id: int) -> str | None:
        return await self.session.scalar(
            select(AiAgentRun.dify_conversation_id)
            .where(
                AiAgentRun.conversation_id == conversation_id,
                AiAgentRun.status == "succeeded",
                AiAgentRun.dify_conversation_id.is_not(None),
            )
            .order_by(AiAgentRun.id.desc())
            .limit(1)
        )

    async def next_sequence(self, conversation_id: int) -> int:
        value = await self.session.scalar(
            select(func.coalesce(func.max(Message.sequence_no), 0) + 1).where(
                Message.conversation_id == conversation_id
            )
        )
        return int(value or 1)
