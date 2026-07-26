from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import Principal
from app.connectors.base import ConnectorContext
from app.connectors.whatsapp.client import (
    REQUIRED_CONFIG_KEYS,
    WhatsAppConnector,
)
from app.connectors.whatsapp.repository import WhatsAppRepository
from app.connectors.whatsapp.schemas import (
    WhatsAppConfigStatusResponse,
    WhatsAppTestResponse,
    WhatsAppWebhookPayload,
    WhatsAppWebhookResponse,
)
from app.core.config import Settings
from app.core.encryption import ConfigCipher
from app.core.exceptions import AppError, ConflictError, ResourceNotFoundError
from app.integrations.dify.client import DifyChatResult, DifyClient
from app.models.ai.ai_agent_run import AiAgentRun
from app.models.auth.tenant import Tenant
from app.models.connector.connector import Connector
from app.models.connector.connector_config import ConnectorConfig
from app.models.connector.webhook_log import WebhookLog
from app.models.conversation.conversation import Conversation
from app.models.conversation.message import Message
from app.models.customer.customer import Customer
from app.models.customer.customer_session import CustomerSession
from app.schemas.protocol import (
    Direction,
    MessageType,
    Party,
    TextContent,
    UnifiedMessageEnvelope,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class WhatsAppRuntime:
    connector: Connector
    tenant: Tenant
    config: dict[str, Any]
    adapter: WhatsAppConnector


class WhatsAppService:
    def __init__(
        self,
        session: AsyncSession,
        repository: WhatsAppRepository,
        settings: Settings,
        cipher: ConfigCipher,
        dify: DifyClient,
    ) -> None:
        self.session = session
        self.repository = repository
        self.settings = settings
        self.cipher = cipher
        self.dify = dify

    async def config_status(
        self,
        principal: Principal,
        connector_id: str,
        webhook_url: str,
    ) -> WhatsAppConfigStatusResponse:
        connector = await self.repository.get_connector_for_update(
            principal.tenant_id,
            connector_id,
        )
        if connector is None:
            raise ResourceNotFoundError("WhatsApp connector")
        configured = sorted(
            config.config_key
            for config in await self.repository.get_configs(connector.id)
            if config.value_encrypted is not None or config.secret_ref is not None
        )
        return WhatsAppConfigStatusResponse(
            connector_id=connector.public_id,
            configured_keys=configured,
            required_keys=list(REQUIRED_CONFIG_KEYS),
            webhook_url=webhook_url,
        )

    async def test_connection(
        self,
        principal: Principal,
        connector_id: str,
    ) -> WhatsAppTestResponse:
        connector = await self.repository.get_connector_for_update(
            principal.tenant_id,
            connector_id,
        )
        if connector is None:
            raise ResourceNotFoundError("WhatsApp connector")
        tenant = Tenant(id=principal.tenant_id, public_id=principal.tenant_public_id)
        runtime = await self._runtime(connector, tenant)
        try:
            result = await runtime.adapter.health_check()
        except Exception as exc:
            connector.status = "error"
            connector.health_status = "unhealthy"
            connector.health_detail = {"message": str(exc)[:500]}
            connector.last_health_check_at = datetime.now(UTC)
            await self.session.commit()
            logger.warning(
                "whatsapp_connector_test_failed tenant_id=%s connector_id=%s error=%s",
                principal.tenant_id,
                connector.public_id,
                type(exc).__name__,
            )
            raise
        connector.status = "active"
        connector.health_status = result.status
        connector.health_detail = {"message": result.message}
        connector.last_health_check_at = result.checked_at
        await self.session.commit()
        logger.info(
            "whatsapp_connector_test_succeeded tenant_id=%s connector_id=%s latency_ms=%s",
            principal.tenant_id,
            connector.public_id,
            result.latency_ms,
        )
        return WhatsAppTestResponse(
            connector_id=connector.public_id,
            status=result.status,
            message=result.message,
            latency_ms=result.latency_ms,
            checked_at=result.checked_at,
        )

    async def verify_subscription(
        self,
        *,
        mode: str | None,
        verify_token: str | None,
        challenge: str | None,
    ) -> str:
        if mode != "subscribe" or not verify_token or challenge is None:
            raise AppError(403, "WHATSAPP_VERIFICATION_FAILED", "Invalid verification request.")
        for connector, config in await self.repository.verification_candidates():
            try:
                stored = self._decrypt(connector, config)
            except Exception:
                logger.warning(
                    "whatsapp_verify_token_decrypt_failed connector_id=%s",
                    connector.public_id,
                )
                continue
            if isinstance(stored, str) and hmac.compare_digest(stored, verify_token):
                logger.info(
                    "whatsapp_webhook_verified connector_id=%s",
                    connector.public_id,
                )
                return challenge
        raise AppError(403, "WHATSAPP_VERIFICATION_FAILED", "Verify token did not match.")

    async def handle_webhook(
        self,
        *,
        raw_body: bytes,
        payload: WhatsAppWebhookPayload,
        payload_dict: dict[str, Any],
        headers: dict[str, str],
    ) -> WhatsAppWebhookResponse:
        phone_number_ids = payload.phone_number_ids()
        if not phone_number_ids:
            return WhatsAppWebhookResponse(status="ignored")
        if len(phone_number_ids) != 1:
            raise AppError(
                422,
                "WHATSAPP_PHONE_NUMBER_AMBIGUOUS",
                "Webhook payload must target exactly one phone number.",
            )
        phone_number_id = next(iter(phone_number_ids))
        context = await self.repository.get_connector_by_phone_number(phone_number_id)
        if context is None:
            raise ResourceNotFoundError("Active WhatsApp connector")
        runtime = await self._runtime(*context)
        configured_account_id = str(runtime.config.get("business_account_id") or "")
        if configured_account_id not in payload.business_account_ids():
            raise AppError(
                403,
                "WHATSAPP_BUSINESS_ACCOUNT_MISMATCH",
                "Webhook business account does not match the connector configuration.",
            )
        try:
            self._verify_signature(
                raw_body,
                headers.get("x-hub-signature-256"),
                runtime.config.get("app_secret"),
            )
        except AppError:
            logger.warning(
                "whatsapp_signature_rejected connector_id=%s request_id=%s",
                runtime.connector.public_id,
                headers.get("x-request-id"),
            )
            raise
        envelopes = await runtime.adapter.normalize_inbound(payload_dict, headers)
        response = WhatsAppWebhookResponse()
        for envelope in envelopes:
            duplicate = await self._process_message(runtime, envelope, headers, raw_body)
            if duplicate:
                response.duplicates += 1
            else:
                response.processed += 1
        return response

    async def _runtime(
        self,
        connector: Connector,
        tenant: Tenant,
    ) -> WhatsAppRuntime:
        configs = await self.repository.get_configs(connector.id)
        values = {
            config.config_key: self._decrypt(connector, config)
            for config in configs
            if config.value_encrypted is not None
        }
        adapter = WhatsAppConnector(
            ConnectorContext(
                tenant_id=tenant.public_id,
                connector_id=connector.public_id,
                config=values,
            ),
            self.settings,
        )
        return WhatsAppRuntime(connector, tenant, values, adapter)

    def _decrypt(self, connector: Connector, config: ConnectorConfig) -> Any:
        if config.value_encrypted is None:
            return None
        return self.cipher.decrypt(
            config.value_encrypted,
            associated_data=f"{connector.tenant_id}:{connector.id}:{config.config_key}",
        )

    @staticmethod
    def _verify_signature(
        raw_body: bytes,
        signature: str | None,
        app_secret: Any,
    ) -> None:
        if not isinstance(app_secret, str) or not app_secret:
            raise AppError(
                503,
                "WHATSAPP_APP_SECRET_REQUIRED",
                "WhatsApp app_secret is required for webhook signature validation.",
            )
        if not signature or not signature.startswith("sha256="):
            raise AppError(403, "WHATSAPP_SIGNATURE_INVALID", "Webhook signature is missing.")
        expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature[7:], expected):
            raise AppError(403, "WHATSAPP_SIGNATURE_INVALID", "Webhook signature is invalid.")

    async def _process_message(
        self,
        runtime: WhatsAppRuntime,
        envelope: UnifiedMessageEnvelope,
        headers: dict[str, str],
        raw_body: bytes,
    ) -> bool:
        event_id = envelope.external_message_id or str(envelope.message_id)
        webhook_log = await self.repository.get_webhook_log(runtime.connector.id, event_id)
        if webhook_log is not None and webhook_log.status == "processed":
            logger.info(
                "whatsapp_webhook_duplicate connector_id=%s event_id=%s",
                runtime.connector.public_id,
                event_id,
            )
            return True
        if webhook_log is None:
            webhook_log = WebhookLog(
                tenant_id=runtime.tenant.id,
                connector_id=runtime.connector.id,
                provider_event_id=event_id,
                event_type="message.received",
                signature_valid=True,
                headers_redacted={
                    "content_type": headers.get("content-type"),
                    "user_agent": headers.get("user-agent"),
                    "request_id": headers.get("x-request-id"),
                    "signature_present": "x-hub-signature-256" in headers,
                },
                payload_redacted={
                    "from": self._redact_phone(envelope.sender.id),
                    "message_type": envelope.context.attributes.get(
                        "provider_message_type"
                    ),
                    "content_length": len(self._text(envelope)),
                },
                payload_hash=hashlib.sha256(raw_body).hexdigest(),
                status="received",
                trace_id=headers.get("x-request-id") or uuid4().hex,
            )
            self.session.add(webhook_log)
            await self.session.flush()

        idempotency_key = f"whatsapp:inbound:{runtime.connector.public_id}:{event_id}"
        context = await self.repository.get_message_context(
            runtime.tenant.id,
            idempotency_key,
        )
        if context is None:
            context = await self._create_inbound_context(
                runtime,
                envelope,
                idempotency_key,
            )
        inbound, conversation, customer_session, customer = context
        run = await self.repository.get_latest_run(inbound.id)
        if run and run.status in {"queued", "running"}:
            now = datetime.now(UTC)
            if (
                run.started_at is not None
                and (now - run.started_at).total_seconds()
                < self.settings.whatsapp_processing_timeout_seconds
            ):
                return True
            run.status = "timed_out"
            run.error_code = "STALE_WHATSAPP_RUN"
            run.error_message = "Recovered a stale WhatsApp processing run."
            run.completed_at = now
            await self.session.commit()
        if run and run.status == "succeeded" and run.output_message_id:
            outbound = await self.repository.get_message(run.output_message_id)
            if outbound is not None:
                if outbound.status == "sent":
                    await self._mark_processed(webhook_log)
                    return True
                await self._send_outbound(runtime, customer_session, outbound, webhook_log)
                return False

        run = AiAgentRun(
            tenant_id=runtime.tenant.id,
            conversation_id=conversation.id,
            trigger_message_id=inbound.id,
            run_type="whatsapp_chat",
            status="running",
            input_redacted={
                "query_length": len(self._text(envelope)),
                "channel": "whatsapp",
            },
            started_at=datetime.now(UTC),
        )
        self.session.add(run)
        webhook_log.status = "processing"
        webhook_log.attempt_count += 1
        await self.session.commit()
        try:
            dify_result = await self.dify.chat(
                query=self._text(envelope),
                user=(
                    f"tenant:{runtime.tenant.public_id}:"
                    f"customer:{customer.public_id}"
                ),
                conversation_id=await self.repository.latest_dify_conversation_id(
                    conversation.id
                ),
                inputs={
                    "channel": "whatsapp",
                    "customer_id": customer.public_id,
                },
            )
        except Exception as exc:
            run.status = "failed"
            run.error_code = getattr(exc, "code", "DIFY_REQUEST_FAILED")
            run.error_message = str(exc)[:1000]
            run.completed_at = datetime.now(UTC)
            self._mark_failed(webhook_log, exc)
            await self.session.commit()
            logger.exception(
                "whatsapp_dify_failed tenant_id=%s connector_id=%s event_id=%s",
                runtime.tenant.id,
                runtime.connector.public_id,
                event_id,
            )
            raise

        outbound = await self._create_outbound(
            runtime,
            conversation.id,
            run,
            dify_result,
        )
        await self._send_outbound(runtime, customer_session, outbound, webhook_log)
        logger.info(
            "whatsapp_message_processed tenant_id=%s connector_id=%s event_id=%s",
            runtime.tenant.id,
            runtime.connector.public_id,
            event_id,
        )
        return False

    async def _create_inbound_context(
        self,
        runtime: WhatsAppRuntime,
        envelope: UnifiedMessageEnvelope,
        idempotency_key: str,
    ) -> tuple[Message, Conversation, CustomerSession, Customer]:
        now = datetime.now(UTC)
        external_contact_id = envelope.sender.id
        context = await self.repository.get_customer_context(
            runtime.tenant.id,
            runtime.connector.id,
            external_contact_id,
        )
        if context is None:
            phone_e164 = self._phone_e164(external_contact_id)
            customer = await self.repository.get_customer_by_phone(
                runtime.tenant.id,
                phone_e164,
            )
            if customer is None:
                customer = Customer(
                    tenant_id=runtime.tenant.id,
                    name=envelope.sender.display_name or phone_e164,
                    phone_e164=phone_e164,
                    language=envelope.context.locale,
                    lifecycle_stage="new",
                    source_type="whatsapp",
                    source_ref=external_contact_id,
                    tags=["whatsapp"],
                    consent_status="unknown",
                    last_contact_at=now,
                )
                self.session.add(customer)
                await self.session.flush()
            customer_session = CustomerSession(
                tenant_id=runtime.tenant.id,
                customer_id=customer.id,
                connector_id=runtime.connector.id,
                external_contact_id=external_contact_id,
                external_thread_id="",
                status="active",
                first_seen_at=now,
                last_seen_at=now,
                metadata_json={
                    "display_name": envelope.sender.display_name,
                    "channel": "whatsapp",
                },
            )
            self.session.add(customer_session)
            await self.session.flush()
        else:
            customer_session, customer = context
            customer_session.last_seen_at = now
            customer.last_contact_at = now
            if envelope.sender.display_name and customer.name == customer.phone_e164:
                customer.name = envelope.sender.display_name

        conversation = await self.repository.get_open_conversation(
            runtime.tenant.id,
            customer_session.id,
        )
        if conversation is None:
            conversation = Conversation(
                tenant_id=runtime.tenant.id,
                customer_id=customer.id,
                customer_session_id=customer_session.id,
                subject=f"WhatsApp - {customer.name}",
                status="open",
                mode="ai",
                ai_enabled=True,
                last_message_at=envelope.occurred_at,
            )
            self.session.add(conversation)
            await self.session.flush()

        inbound = Message(
            tenant_id=runtime.tenant.id,
            conversation_id=conversation.id,
            connector_id=runtime.connector.id,
            sequence_no=await self.repository.next_sequence(conversation.id),
            direction="inbound",
            sender_type="customer",
            sender_ref=external_contact_id,
            message_type="text",
            content_text=self._text(envelope),
            content_json={
                "provider_message_type": envelope.context.attributes.get(
                    "provider_message_type"
                ),
                "provider_content": envelope.context.attributes.get("provider_content"),
            },
            external_message_id=envelope.external_message_id,
            idempotency_key=idempotency_key,
            status="received",
            created_at=envelope.occurred_at,
        )
        self.session.add(inbound)
        conversation.last_message_at = envelope.occurred_at
        conversation.unread_count += 1
        conversation.version += 1
        await self.session.flush()
        return inbound, conversation, customer_session, customer

    async def _create_outbound(
        self,
        runtime: WhatsAppRuntime,
        conversation_id: int,
        run: AiAgentRun,
        result: DifyChatResult,
    ) -> Message:
        conversation = await self.repository.get_conversation_for_update(conversation_id)
        if conversation is None:
            raise ResourceNotFoundError("Conversation")
        now = datetime.now(UTC)
        outbound = Message(
            tenant_id=runtime.tenant.id,
            conversation_id=conversation.id,
            connector_id=runtime.connector.id,
            sequence_no=await self.repository.next_sequence(conversation.id),
            direction="outbound",
            sender_type="ai",
            sender_ref=run.public_id,
            message_type="text",
            content_text=result.answer,
            idempotency_key=f"whatsapp:agent:{run.public_id}",
            status="queued",
            citations=result.citations,
            token_usage={
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
            },
            created_at=now,
        )
        self.session.add(outbound)
        await self.session.flush()
        run.output_message_id = outbound.id
        run.status = "succeeded"
        run.dify_conversation_id = result.conversation_id
        run.dify_task_id = result.task_id
        run.output_redacted = {"answer_length": len(result.answer)}
        run.citations = result.citations
        run.prompt_tokens = result.prompt_tokens
        run.completion_tokens = result.completion_tokens
        run.cost_amount = result.total_price
        run.cost_currency = result.currency
        run.latency_ms = result.latency_ms
        run.completed_at = now
        conversation.last_message_at = now
        conversation.version += 1
        await self.session.commit()
        return outbound

    async def _send_outbound(
        self,
        runtime: WhatsAppRuntime,
        customer_session: CustomerSession,
        outbound: Message,
        webhook_log: WebhookLog,
    ) -> None:
        envelope = UnifiedMessageEnvelope(
            external_message_id=None,
            idempotency_key=outbound.idempotency_key,
            tenant_id=runtime.tenant.public_id,
            channel="whatsapp",
            direction=Direction.OUTBOUND,
            message_type=MessageType.TEXT,
            conversation_id=str(outbound.conversation_id),
            sender=Party(id=str(runtime.config["phone_number_id"])),
            recipients=[Party(id=customer_session.external_contact_id)],
            content=TextContent(text=outbound.content_text or ""),
        )
        try:
            result = await runtime.adapter.send(envelope)
            if not result.accepted:
                raise ConflictError(
                    "WHATSAPP_SEND_REJECTED",
                    result.detail or "WhatsApp rejected the outbound message.",
                )
        except Exception as exc:
            outbound.status = "failed"
            outbound.error_code = getattr(exc, "code", "WHATSAPP_SEND_FAILED")
            self._mark_failed(webhook_log, exc)
            await self.session.commit()
            logger.exception(
                "whatsapp_send_failed tenant_id=%s connector_id=%s message_id=%s",
                runtime.tenant.id,
                runtime.connector.public_id,
                outbound.public_id,
            )
            raise
        outbound.status = "sent"
        outbound.external_message_id = result.provider_request_id
        outbound.sent_at = datetime.now(UTC)
        await self._mark_processed(webhook_log)

    async def _mark_processed(self, webhook_log: WebhookLog) -> None:
        webhook_log.status = "processed"
        webhook_log.processed_at = datetime.now(UTC)
        webhook_log.error_code = None
        webhook_log.error_message = None
        await self.session.commit()

    @staticmethod
    def _mark_failed(webhook_log: WebhookLog, exc: Exception) -> None:
        webhook_log.status = "failed"
        webhook_log.error_code = getattr(exc, "code", type(exc).__name__)[:120]
        webhook_log.error_message = str(exc)[:1000]

    @staticmethod
    def _text(envelope: UnifiedMessageEnvelope) -> str:
        if not isinstance(envelope.content, TextContent):
            raise ConflictError(
                "WHATSAPP_MESSAGE_UNSUPPORTED",
                "Only normalized text messages can be processed.",
            )
        return envelope.content.text

    @staticmethod
    def _phone_e164(value: str) -> str:
        digits = "".join(character for character in value if character.isdigit())
        return f"+{digits}"[:32]

    @staticmethod
    def _redact_phone(value: str) -> str:
        return f"***{value[-4:]}" if len(value) > 4 else "****"
