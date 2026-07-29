from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import Principal
from app.connectors.base import ConnectorContext
from app.connectors.whatsapp.client import (
    REQUIRED_CONFIG_KEYS,
    OpenWAClient,
    WhatsAppConnector,
)
from app.connectors.whatsapp.repository import WhatsAppRepository
from app.connectors.whatsapp.schemas import (
    OpenWAQRCodeResponse,
    OpenWASessionStatusResponse,
    WhatsAppConfigStatusResponse,
    WhatsAppSendResponse,
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
from app.models.connector.whatsapp_session import WhatsAppSession
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

    async def session_status(
        self,
        principal: Principal,
    ) -> OpenWASessionStatusResponse:
        connector, tenant, whatsapp_session = await self._management_session(
            principal,
            for_update=True,
        )
        result = await self._client(whatsapp_session).session_status()
        self._apply_session_status(connector, whatsapp_session, result)
        await self.session.commit()
        return result

    async def create_session(
        self,
        principal: Principal,
    ) -> OpenWASessionStatusResponse:
        connector, tenant, whatsapp_session = await self._management_session(
            principal,
            for_update=True,
        )
        client = self._client(whatsapp_session)
        result = await client.create_session()
        await self._assert_unclaimed(
            connector,
            session_name=result.name or whatsapp_session.session_name,
            session_id=result.session_id,
        )
        self._apply_session_status(connector, whatsapp_session, result)
        await self._commit_session_lifecycle()
        logger.info(
            "whatsapp_session_created_or_reused tenant_id=%s connector_id=%s "
            "openwa_session_id=%s status=%s",
            tenant.id,
            connector.public_id,
            whatsapp_session.session_id,
            whatsapp_session.status,
        )
        return result

    async def qrcode(
        self,
        principal: Principal,
    ) -> OpenWAQRCodeResponse:
        connector, tenant, whatsapp_session = await self._management_session(
            principal,
            for_update=True,
        )
        client = self._client(whatsapp_session)
        result = await client.qrcode()
        await self._assert_unclaimed(
            connector,
            session_name=client.session_name,
            session_id=client.session_id,
        )
        whatsapp_session.session_id = client.session_id
        connector.session_id = client.session_id
        whatsapp_session.session_name = client.session_name
        whatsapp_session.status = result.status
        whatsapp_session.session_data = {
            **(whatsapp_session.session_data or {}),
            "openwa_session_id": client.session_id,
            "session_name": client.session_name,
            "status": result.status,
            "observed_at": datetime.now(UTC).isoformat(),
        }
        if result.data_url:
            whatsapp_session.qr_code = result.data_url
        elif result.status in {"connected", "disconnected", "error"}:
            whatsapp_session.qr_code = None
        if result.status == "connected":
            whatsapp_session.last_connected_at = datetime.now(UTC)
            connector.status = "active"
            connector.health_status = "healthy"
        await self._commit_session_lifecycle()
        logger.info(
            "whatsapp_qr_status tenant_id=%s connector_id=%s "
            "openwa_session_id=%s status=%s qr_available=%s",
            tenant.id,
            connector.public_id,
            whatsapp_session.session_id,
            result.status,
            bool(result.data_url),
        )
        return result

    async def delete_session(
        self,
        principal: Principal,
    ) -> OpenWASessionStatusResponse:
        connector, _, whatsapp_session = await self._management_session(
            principal,
            for_update=True,
        )
        result = await self._client(whatsapp_session).delete_session()
        whatsapp_session.session_id = None
        whatsapp_session.status = "disconnected"
        whatsapp_session.qr_code = None
        whatsapp_session.last_error = None
        whatsapp_session.session_data = None
        connector.session_id = None
        connector.status = "draft"
        connector.health_status = None
        await self.session.commit()
        return result

    async def reconnect_session(
        self,
        principal: Principal,
    ) -> OpenWASessionStatusResponse:
        connector, _, whatsapp_session = await self._management_session(
            principal,
            for_update=True,
        )
        client = self._client(whatsapp_session)
        result = await client.reconnect()
        await self._assert_unclaimed(
            connector,
            session_name=client.session_name,
            session_id=client.session_id,
        )
        self._apply_session_status(connector, whatsapp_session, result)
        await self._commit_session_lifecycle()
        return result

    async def send_message(
        self,
        principal: Principal,
        recipient: str,
        text: str,
    ) -> WhatsAppSendResponse:
        connector, _, whatsapp_session = await self._management_session(principal)
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

        status = await self._client(whatsapp_session).session_status()
        self._apply_session_status(connector, whatsapp_session, status)
        await self.session.commit()
        if status.status != "connected":
            raise ConflictError(
                "WHATSAPP_SESSION_NOT_CONNECTED",
                "The tenant WhatsApp session is not connected.",
            )
        return await self._client(whatsapp_session).send_text(recipient, text)

    async def _management_session(
        self,
        principal: Principal,
        *,
        for_update: bool = False,
    ) -> tuple[Connector, Tenant, WhatsAppSession]:
        context = await self.repository.get_management_context(
            principal.tenant_id,
            for_update=for_update,
        )
        if context is None:
            raise ResourceNotFoundError("Tenant WhatsApp connector")
        connector, tenant = context
        session_name = await self._desired_session_name(connector)
        whatsapp_session = await self.repository.get_whatsapp_session(
            principal.tenant_id,
            connector.id,
            for_update=for_update,
        )
        if whatsapp_session is None:
            await self._assert_unclaimed(
                connector,
                session_name=session_name,
                session_id=connector.session_id,
            )
            whatsapp_session = WhatsAppSession(
                tenant_id=principal.tenant_id,
                connector_id=connector.id,
                session_id=connector.session_id,
                session_name=session_name,
                status="created",
            )
            self.repository.add_whatsapp_session(whatsapp_session)
            try:
                await self.session.flush()
            except IntegrityError as exc:
                await self.session.rollback()
                raise ConflictError(
                    "WHATSAPP_SESSION_ALREADY_CLAIMED",
                    "This OpenWA session is already assigned to another tenant connector.",
                ) from exc
        elif (
            whatsapp_session.session_name != session_name
            and whatsapp_session.session_id is None
        ):
            await self._assert_unclaimed(
                connector,
                session_name=session_name,
                session_id=None,
            )
            whatsapp_session.session_name = session_name
        if connector.session_id and whatsapp_session.session_id is None:
            whatsapp_session.session_id = connector.session_id
        elif whatsapp_session.session_id and connector.session_id is None:
            connector.session_id = whatsapp_session.session_id
        elif (
            connector.session_id
            and whatsapp_session.session_id
            and connector.session_id != whatsapp_session.session_id
        ):
            raise ConflictError(
                "WHATSAPP_SESSION_BINDING_MISMATCH",
                "Connector and WhatsApp session bindings do not match.",
            )
        return connector, tenant, whatsapp_session

    async def _desired_session_name(self, connector: Connector) -> str:
        configs = await self.repository.get_configs(connector.id)
        configured = next(
            (
                self._decrypt(connector, config)
                for config in configs
                if config.config_key == "session_id"
                and config.value_encrypted is not None
            ),
            None,
        )
        external = (
            connector.external_account_id
            if connector.external_account_id != "demo-template"
            else None
        )
        return OpenWAClient._resolve_session_name(
            str(configured or external or ""),
            self.settings.openwa_session_name,
        )

    def _client(self, whatsapp_session: WhatsAppSession) -> OpenWAClient:
        return OpenWAClient(
            self.settings,
            session_id=whatsapp_session.session_id,
            session_name=whatsapp_session.session_name,
        )

    async def _assert_unclaimed(
        self,
        connector: Connector,
        *,
        session_name: str,
        session_id: str | None,
    ) -> None:
        claim = await self.repository.get_session_claim(
            session_name=session_name,
            session_id=session_id,
            exclude_connector_id=connector.id,
        )
        if claim is not None:
            raise ConflictError(
                "WHATSAPP_SESSION_ALREADY_CLAIMED",
                "This OpenWA session is already assigned to another tenant connector.",
            )

    @staticmethod
    def _apply_session_status(
        connector: Connector,
        whatsapp_session: WhatsAppSession,
        result: OpenWASessionStatusResponse,
    ) -> None:
        if result.session_id:
            whatsapp_session.session_id = result.session_id
            connector.session_id = result.session_id
        if result.name:
            whatsapp_session.session_name = result.name
        whatsapp_session.phone = result.phone_number
        whatsapp_session.status = result.status
        whatsapp_session.last_error = result.last_error
        whatsapp_session.session_data = {
            **(result.session_data or {}),
            "openwa_session_id": whatsapp_session.session_id,
            "session_name": whatsapp_session.session_name,
            "phone": result.phone_number,
            "status": result.status,
            "observed_at": datetime.now(UTC).isoformat(),
        }
        if result.status == "connected":
            whatsapp_session.qr_code = None
            whatsapp_session.last_connected_at = datetime.now(UTC)
            whatsapp_session.last_error = None
            connector.status = "active"
            connector.health_status = "healthy"
            connector.health_detail = {"message": "WhatsApp session is connected."}
        elif result.status == "error":
            whatsapp_session.qr_code = None
            connector.status = "error"
            connector.health_status = "unhealthy"
            connector.health_detail = {
                "message": result.last_error or "OpenWA session reported an error."
            }
        else:
            connector.status = "draft"
            connector.health_status = "degraded"
            connector.health_detail = {
                "message": f"WhatsApp session is {result.status}."
            }
        connector.last_health_check_at = datetime.now(UTC)

    async def _commit_session_lifecycle(self) -> None:
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError(
                "WHATSAPP_SESSION_ALREADY_CLAIMED",
                "This OpenWA session is already assigned to another tenant connector.",
            ) from exc

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

    async def handle_webhook(
        self,
        *,
        raw_body: bytes,
        payload: WhatsAppWebhookPayload,
        payload_dict: dict[str, Any],
        headers: dict[str, str],
    ) -> WhatsAppWebhookResponse:
        try:
            self._verify_signature(
                raw_body,
                headers.get("x-openwa-signature"),
                self.settings.openwa_api_key,
            )
        except AppError:
            logger.warning(
                "openwa_signature_rejected session_id=%s request_id=%s",
                payload.session_id,
                headers.get("x-request-id"),
            )
            raise
        if payload.event not in {"message.received", "message.sent"}:
            return WhatsAppWebhookResponse(status="ignored")
        context = await self.repository.get_connector_by_session(payload.session_id)
        if context is None:
            raise ResourceNotFoundError("Active WhatsApp connector")
        whatsapp_session = await self.repository.get_whatsapp_session(
            context[0].tenant_id,
            context[0].id,
            for_update=True,
        )
        if whatsapp_session is None:
            raise ResourceNotFoundError("Tenant WhatsApp session")
        now = datetime.now(UTC)
        whatsapp_session.status = "connected"
        whatsapp_session.last_connected_at = now
        whatsapp_session.last_error = None
        whatsapp_session.session_data = {
            **(whatsapp_session.session_data or {}),
            "last_webhook_event": payload.event,
            "last_webhook_at": now.isoformat(),
            "last_delivery_id": payload.delivery_id,
        }
        context[0].status = "active"
        context[0].health_status = "healthy"
        context[0].health_detail = {"message": "WhatsApp webhook is active."}
        context[0].last_health_check_at = now
        if payload.event == "message.sent":
            await self.session.commit()
            return WhatsAppWebhookResponse(status="accepted")
        runtime = await self._runtime(*context)
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
        values.setdefault("session_id", self.settings.openwa_session_name)
        whatsapp_session = await self.repository.get_whatsapp_session(
            connector.tenant_id,
            connector.id,
        )
        if whatsapp_session and whatsapp_session.session_id:
            values["openwa_session_id"] = whatsapp_session.session_id
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
        webhook_secret: Any,
    ) -> None:
        if not isinstance(webhook_secret, str) or not webhook_secret:
            raise AppError(
                503,
                "OPENWA_API_KEY_REQUIRED",
                "OPENWA_API_KEY is required for webhook signature validation.",
            )
        if not signature or not signature.startswith("sha256="):
            raise AppError(403, "WHATSAPP_SIGNATURE_INVALID", "Webhook signature is missing.")
        expected = hmac.new(webhook_secret.encode(), raw_body, hashlib.sha256).hexdigest()
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
                    "signature_present": "x-openwa-signature" in headers,
                    "openwa_delivery_id": headers.get("x-openwa-delivery-id"),
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
            sender=Party(id=str(runtime.config["session_id"])),
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
