from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import Principal
from app.connectors.base import ConnectorContext
from app.connectors.whatsapp.client import (
    DEFAULT_ADAPTER,
    WhatsAppConnector,
    required_config_keys,
)
from app.connectors.whatsapp.repository import WhatsAppRepository
from app.connectors.whatsapp.schemas import (
    WhatsAppConfigStatusResponse,
    WhatsAppGatewayInboundRequest,
    WhatsAppSendResponse,
    WhatsAppTestResponse,
    WhatsAppWebhookResponse,
)
from app.core.config import Settings
from app.core.encryption import ConfigCipher
from app.core.exceptions import (
    ConflictError,
    ResourceNotFoundError,
    ServiceConfigurationError,
)
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
from app.models.system.outbox_event import OutboxEvent
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
        adapter = await self._configured_adapter(connector)
        return WhatsAppConfigStatusResponse(
            connector_id=connector.public_id,
            adapter=adapter,
            configured_keys=configured,
            required_keys=list(required_config_keys(adapter)),
            webhook_url=webhook_url,
        )

    async def test_connection(
        self,
        principal: Principal,
        connector_id: str,
    ) -> WhatsAppTestResponse:
        context = await self.repository.get_connector_context(
            principal.tenant_id,
            connector_id,
            for_update=True,
        )
        if context is None:
            raise ResourceNotFoundError("WhatsApp connector")
        connector, tenant = context
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
        connector.health_detail = {
            "message": result.message,
            "adapter": runtime.adapter.adapter_key,
        }
        connector.last_health_check_at = result.checked_at
        connector.last_connected_at = result.checked_at
        connector.last_disconnect_reason = None
        await self.session.commit()
        return WhatsAppTestResponse(
            connector_id=connector.public_id,
            status=result.status,
            message=result.message,
            latency_ms=result.latency_ms,
            checked_at=result.checked_at,
        )

    async def verify_webhook(
        self,
        connector_id: str,
        *,
        mode: str,
        token: str,
        challenge: str,
    ) -> str:
        context = await self.repository.get_connector_context_by_public_id(connector_id)
        if context is None:
            raise ResourceNotFoundError("Active WhatsApp connector")
        runtime = await self._runtime(*context)
        return runtime.adapter.verify_challenge(mode, token, challenge)

    async def handle_webhook(
        self,
        connector_id: str,
        *,
        raw_body: bytes,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> WhatsAppWebhookResponse:
        context = await self.repository.get_connector_context_by_public_id(
            connector_id,
            for_update=True,
        )
        if context is None:
            raise ResourceNotFoundError("Active WhatsApp connector")
        runtime = await self._runtime(*context)
        envelopes = await runtime.adapter.normalize_inbound(payload, headers, raw_body)
        response = WhatsAppWebhookResponse()
        for envelope in envelopes:
            duplicate = await self._process_message(runtime, envelope, headers, raw_body)
            if duplicate:
                response.duplicates += 1
            else:
                response.processed += 1
        return response

    async def handle_gateway_message(
        self,
        payload: WhatsAppGatewayInboundRequest,
        *,
        raw_body: bytes,
        headers: dict[str, str],
    ) -> WhatsAppWebhookResponse:
        connector_id = payload.connector_id or self.settings.whatsapp_gateway_connector_id
        if not connector_id:
            raise ServiceConfigurationError(
                "connector_id or WHATSAPP_GATEWAY_CONNECTOR_ID is required."
            )
        session_id = payload.session_id or self.settings.whatsapp_gateway_session_id
        context = await self.repository.get_connector_context_by_public_id(
            connector_id,
            for_update=True,
        )
        if context is None:
            raise ResourceNotFoundError("Active WhatsApp connector")
        connector, tenant = context
        runtime = self._gateway_runtime(
            connector,
            tenant,
            session_id=session_id,
        )
        envelopes = await runtime.adapter.normalize_inbound(
            payload.model_dump(),
            headers,
            raw_body,
        )
        response = WhatsAppWebhookResponse()
        for envelope in envelopes:
            duplicate = await self._process_message(runtime, envelope, headers, raw_body)
            if duplicate:
                response.duplicates += 1
            else:
                response.processed += 1
        return response

    async def send_message(
        self,
        principal: Principal,
        recipient: str,
        text: str,
    ) -> WhatsAppSendResponse:
        context = await self.repository.get_management_context(principal.tenant_id)
        if context is None:
            raise ResourceNotFoundError("Tenant WhatsApp connector")
        connector, tenant = context
        digits = "".join(character for character in recipient if character.isdigit())
        customer = await self.repository.get_customer_by_phone(
            principal.tenant_id,
            f"+{digits}",
        )
        if customer is None:
            raise ResourceNotFoundError("Tenant customer")
        can_send_all = bool(
            principal.permissions.intersection(
                {
                    "connector.manage",
                    "conversation.read_all",
                    "customer.read_all",
                }
            )
        )
        if not can_send_all and customer.owner_user_id != principal.user_id:
            raise ResourceNotFoundError("Assigned customer")

        runtime = await self._runtime(connector, tenant)
        envelope = UnifiedMessageEnvelope(
            idempotency_key=f"whatsapp:manual:{uuid4().hex}",
            tenant_id=tenant.public_id,
            channel="whatsapp",
            direction=Direction.OUTBOUND,
            message_type=MessageType.TEXT,
            conversation_id=digits,
            sender=Party(id=str(runtime.config.get("phone_number_id") or connector.public_id)),
            recipients=[Party(id=recipient)],
            content=TextContent(text=text),
        )
        result = await runtime.adapter.send(envelope)
        if not result.accepted or not result.provider_request_id:
            raise ConflictError(
                "WHATSAPP_SEND_REJECTED",
                result.detail or "WhatsApp provider rejected the outbound message.",
            )
        return WhatsAppSendResponse(message_id=result.provider_request_id)

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
        values.setdefault("adapter", DEFAULT_ADAPTER)
        adapter = WhatsAppConnector(
            ConnectorContext(
                tenant_id=tenant.public_id,
                connector_id=connector.public_id,
                config=values,
            ),
            self.settings,
        )
        return WhatsAppRuntime(connector, tenant, values, adapter)

    def _gateway_runtime(
        self,
        connector: Connector,
        tenant: Tenant,
        *,
        session_id: str,
    ) -> WhatsAppRuntime:
        values = {
            "adapter": "webjs_gateway",
            "gateway_url": self.settings.whatsapp_gateway_url,
            "gateway_token": self.settings.whatsapp_gateway_token,
            "session_id": session_id,
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

    async def _configured_adapter(self, connector: Connector) -> str:
        for config in await self.repository.get_configs(connector.id):
            if config.config_key == "adapter" and config.value_encrypted is not None:
                return str(self._decrypt(connector, config))
        return DEFAULT_ADAPTER

    def _decrypt(self, connector: Connector, config: ConnectorConfig) -> Any:
        if config.value_encrypted is None:
            return None
        return self.cipher.decrypt(
            config.value_encrypted,
            associated_data=f"{connector.tenant_id}:{connector.id}:{config.config_key}",
        )

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
                    "provider_adapter": runtime.adapter.adapter_key,
                    "gateway_session_id": runtime.config.get("session_id"),
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
        if webhook_log.status == "retry_pending":
            logger.info(
                "whatsapp_ai_retry_already_pending request_id=%s customer_id=%s "
                "conversation_id=%s error_code=%s retry_count=%s final_status=pending",
                webhook_log.trace_id,
                customer.public_id,
                conversation.public_id,
                webhook_log.error_code,
                webhook_log.attempt_count,
            )
            return True
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
                user=customer.public_id,
                conversation_id=None,
                inputs={},
                request_context={
                    "request_id": webhook_log.trace_id,
                    "customer_id": customer.public_id,
                    "conversation_id": conversation.public_id,
                },
            )
        except Exception as exc:
            retry_count = int(getattr(exc, "retry_count", 0))
            run.status = "failed"
            run.error_code = getattr(exc, "code", "DIFY_REQUEST_FAILED")
            run.error_message = str(exc)[:1000]
            run.input_redacted = {
                **(run.input_redacted or {}),
                "request_id": webhook_log.trace_id,
                "customer_id": customer.public_id,
                "conversation_id": conversation.public_id,
                "retry_count": retry_count,
                "final_status": "pending_background",
            }
            run.completed_at = datetime.now(UTC)
            self._mark_failed(webhook_log, exc)
            webhook_log.status = "retry_pending"
            webhook_log.attempt_count = retry_count
            webhook_log.next_retry_at = datetime.now(UTC) + timedelta(seconds=5)
            self.session.add(
                OutboxEvent(
                    tenant_id=runtime.tenant.id,
                    aggregate_type="whatsapp_ai_retry",
                    aggregate_id=webhook_log.public_id,
                    event_type="ai.whatsapp.retry.requested.v1",
                    payload={
                        "webhook_log_id": webhook_log.public_id,
                        "request_id": webhook_log.trace_id,
                        "customer_id": customer.public_id,
                        "conversation_id": conversation.public_id,
                        "error_code": run.error_code,
                        "retry_count": retry_count,
                        "final_status": "pending_background",
                    },
                    available_at=webhook_log.next_retry_at,
                )
            )
            await self.session.commit()
            logger.error(
                "whatsapp_ai_request_final request_id=%s customer_id=%s "
                "conversation_id=%s error_code=%s retry_count=%s "
                "final_status=pending_background",
                webhook_log.trace_id,
                customer.public_id,
                conversation.public_id,
                run.error_code,
                retry_count,
                exc_info=True,
            )
            return False

        run.input_redacted = {
            **(run.input_redacted or {}),
            "request_id": webhook_log.trace_id,
            "customer_id": customer.public_id,
            "conversation_id": conversation.public_id,
            "retry_count": dify_result.retry_count,
            "final_status": "succeeded",
        }

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

    async def retry_pending_webhook(self, webhook_log_id: str) -> None:
        retry_context = await self.repository.get_webhook_retry_context(webhook_log_id)
        if retry_context is None:
            raise ResourceNotFoundError("WhatsApp AI retry task")
        webhook_log, connector, tenant = retry_context
        if webhook_log.status == "processed":
            return

        if (webhook_log.headers_redacted or {}).get("provider_adapter") == "webjs_gateway":
            session_id = str(
                (webhook_log.headers_redacted or {}).get("gateway_session_id") or ""
            )
            runtime = self._gateway_runtime(connector, tenant, session_id=session_id)
        else:
            runtime = await self._runtime(connector, tenant)
        idempotency_key = (
            f"whatsapp:inbound:{connector.public_id}:{webhook_log.provider_event_id}"
        )
        message_context = await self.repository.get_message_context(
            tenant.id,
            idempotency_key,
        )
        if message_context is None:
            raise ResourceNotFoundError("WhatsApp inbound message")
        inbound, conversation, customer_session, customer = message_context

        previous_run = await self.repository.get_latest_run(inbound.id)
        if previous_run and previous_run.status == "succeeded" and previous_run.output_message_id:
            outbound = await self.repository.get_message(previous_run.output_message_id)
            if outbound is not None:
                if outbound.status != "sent":
                    await self._send_outbound(
                        runtime,
                        customer_session,
                        outbound,
                        webhook_log,
                    )
                else:
                    await self._mark_processed(webhook_log)
                return

        run = AiAgentRun(
            tenant_id=tenant.id,
            conversation_id=conversation.id,
            trigger_message_id=inbound.id,
            run_type="whatsapp_chat_retry",
            status="running",
            input_redacted={
                "query_length": len(inbound.content_text or ""),
                "channel": "whatsapp",
                "request_id": webhook_log.trace_id,
                "customer_id": customer.public_id,
                "conversation_id": conversation.public_id,
                "final_status": "running_background",
            },
            started_at=datetime.now(UTC),
        )
        self.session.add(run)
        webhook_log.status = "processing"
        webhook_log.attempt_count += 1
        await self.session.commit()

        try:
            result = await self.dify.chat(
                query=inbound.content_text or "",
                user=customer.public_id,
                conversation_id=None,
                inputs={},
                request_context={
                    "request_id": webhook_log.trace_id,
                    "customer_id": customer.public_id,
                    "conversation_id": conversation.public_id,
                },
            )
        except Exception as exc:
            retry_count = int(getattr(exc, "retry_count", 0))
            run.status = "failed"
            run.error_code = getattr(exc, "code", "DIFY_REQUEST_FAILED")
            run.error_message = str(exc)[:1000]
            run.input_redacted = {
                **(run.input_redacted or {}),
                "retry_count": retry_count,
                "final_status": "pending_background",
            }
            run.completed_at = datetime.now(UTC)
            self._mark_failed(webhook_log, exc)
            webhook_log.status = "retry_pending"
            await self.session.commit()
            raise

        run.input_redacted = {
            **(run.input_redacted or {}),
            "retry_count": result.retry_count,
            "final_status": "succeeded",
        }
        outbound = await self._create_outbound(
            runtime,
            conversation.id,
            run,
            result,
        )
        await self._send_outbound(runtime, customer_session, outbound, webhook_log)

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
            source="whatsapp",
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
            source="whatsapp",
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
            sender=Party(
                id=str(runtime.config.get("phone_number_id") or runtime.connector.public_id)
            ),
            recipients=[Party(id=customer_session.external_contact_id)],
            content=TextContent(text=outbound.content_text or ""),
        )
        try:
            result = await runtime.adapter.send(envelope)
            if not result.accepted:
                raise ConflictError(
                    "WHATSAPP_SEND_REJECTED",
                    result.detail or "WhatsApp provider rejected the outbound message.",
                )
        except Exception as exc:
            outbound.status = "failed"
            outbound.error_code = getattr(exc, "code", "WHATSAPP_SEND_FAILED")
            outbound.content_json = {
                **(outbound.content_json or {}),
                "send_error": str(exc)[:1000],
            }
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
        webhook_log.next_retry_at = None
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
