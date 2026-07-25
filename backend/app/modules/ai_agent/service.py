from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import Principal
from app.core.exceptions import ConflictError, ResourceNotFoundError
from app.integrations.dify.client import DifyChatResult, DifyClient
from app.models.ai.ai_agent_run import AiAgentRun
from app.models.conversation.message import Message
from app.models.system.outbox_event import OutboxEvent
from app.modules.ai_agent.repository import AiAgentRepository
from app.modules.ai_agent.schemas import AgentChatRequest, AgentChatResponse, AgentUsage


class AiAgentService:
    def __init__(
        self,
        session: AsyncSession,
        repository: AiAgentRepository,
        dify: DifyClient,
    ) -> None:
        self.session = session
        self.repository = repository
        self.dify = dify

    async def chat(
        self,
        principal: Principal,
        payload: AgentChatRequest,
    ) -> AgentChatResponse:
        context = await self.repository.get_conversation_for_update(
            principal.tenant_id,
            payload.conversation_id,
        )
        if context is None:
            raise ResourceNotFoundError("Conversation")
        conversation, customer_public_id, connector_id = context
        if not conversation.ai_enabled or conversation.mode == "human":
            raise ConflictError(
                "AI_NOT_AVAILABLE",
                "AI is disabled or the conversation is in human mode.",
            )
        if conversation.status in {"closed", "blocked"}:
            raise ConflictError(
                "CONVERSATION_NOT_WRITABLE",
                "AI cannot reply to a closed or blocked conversation.",
            )

        existing_message = await self.repository.get_message_by_idempotency(
            principal.tenant_id,
            payload.idempotency_key,
        )
        if existing_message is not None:
            if existing_message.conversation_id != conversation.id:
                raise ConflictError(
                    "IDEMPOTENCY_KEY_REUSED",
                    "Idempotency key was already used for another conversation.",
                )
            return await self._existing_response(
                existing_message,
                conversation.public_id,
            )

        now = datetime.now(UTC)
        trigger_message = Message(
            tenant_id=principal.tenant_id,
            conversation_id=conversation.id,
            connector_id=connector_id,
            sequence_no=await self.repository.next_sequence(conversation.id),
            direction="internal",
            sender_type="user",
            sender_ref=principal.user_public_id,
            message_type="text",
            content_text=payload.query,
            content_json={"inputs": payload.inputs} if payload.inputs else None,
            idempotency_key=payload.idempotency_key,
            status="received",
            created_at=now,
        )
        self.repository.add(trigger_message)
        await self.session.flush()

        run = AiAgentRun(
            tenant_id=principal.tenant_id,
            conversation_id=conversation.id,
            trigger_message_id=trigger_message.id,
            run_type="chat",
            status="running",
            input_redacted={
                "query_length": len(payload.query),
                "input_keys": sorted(payload.inputs),
            },
            started_at=now,
        )
        self.repository.add(run)
        await self.session.commit()

        dify_conversation_id = await self.repository.latest_dify_conversation_id(conversation.id)
        try:
            result = await self.dify.chat(
                query=payload.query,
                user=f"tenant:{principal.tenant_public_id}:customer:{customer_public_id}",
                conversation_id=dify_conversation_id,
                inputs=payload.inputs,
            )
        except Exception as exc:
            run.status = "failed"
            run.error_code = getattr(exc, "code", "DIFY_REQUEST_FAILED")
            run.error_message = str(exc)[:1000]
            run.completed_at = datetime.now(UTC)
            await self.session.commit()
            raise

        return await self._complete_run(
            principal,
            conversation,
            connector_id,
            run,
            result,
        )

    async def _complete_run(
        self,
        principal: Principal,
        conversation: Any,
        connector_id: int,
        run: AiAgentRun,
        result: DifyChatResult,
    ) -> AgentChatResponse:
        now = datetime.now(UTC)
        # Lock again because the external Dify request intentionally ran outside a DB transaction.
        context = await self.repository.get_conversation_for_update(
            principal.tenant_id,
            conversation.public_id,
        )
        if context is None:
            raise ResourceNotFoundError("Conversation")
        locked_conversation = context[0]

        output_message = Message(
            tenant_id=principal.tenant_id,
            conversation_id=locked_conversation.id,
            connector_id=connector_id,
            sequence_no=await self.repository.next_sequence(locked_conversation.id),
            direction="outbound",
            sender_type="ai",
            sender_ref=run.public_id,
            message_type="text",
            content_text=result.answer,
            idempotency_key=f"agent:{run.public_id}",
            status="queued",
            citations=result.citations,
            token_usage={
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
            },
            created_at=now,
        )
        self.repository.add(output_message)
        await self.session.flush()
        self.session.add(
            OutboxEvent(
                tenant_id=principal.tenant_id,
                aggregate_type="conversation",
                aggregate_id=locked_conversation.public_id,
                event_type="connector.message.send.requested.v1",
                payload={
                    "message_id": output_message.public_id,
                    "conversation_id": locked_conversation.public_id,
                    "ai_run_id": run.public_id,
                },
                available_at=now,
            )
        )

        run.output_message_id = output_message.id
        run.status = "succeeded"
        run.dify_conversation_id = result.conversation_id
        run.dify_task_id = result.task_id
        run.output_redacted = {"answer": result.answer}
        run.citations = result.citations
        run.prompt_tokens = result.prompt_tokens
        run.completion_tokens = result.completion_tokens
        run.cost_amount = result.total_price
        run.cost_currency = result.currency
        run.latency_ms = result.latency_ms
        run.completed_at = now
        locked_conversation.last_message_at = now
        locked_conversation.version += 1
        await self.session.commit()
        return self._response(run, output_message, locked_conversation.public_id, result)

    async def _existing_response(
        self,
        trigger_message: Message,
        conversation_public_id: str,
    ) -> AgentChatResponse:
        run = await self.repository.get_run_by_trigger_message(trigger_message.id)
        if run is None or run.status in {"queued", "running"}:
            raise ConflictError(
                "AI_RUN_IN_PROGRESS",
                "An AI run with this idempotency key is still in progress.",
            )
        if run.status != "succeeded" or run.output_message_id is None:
            raise ConflictError(
                "AI_RUN_NOT_REUSABLE",
                "The previous AI run failed; submit a new idempotency key.",
            )
        output_message = await self.repository.get_message(run.output_message_id)
        if output_message is None:
            raise ResourceNotFoundError("AI output message")
        result = DifyChatResult(
            answer=output_message.content_text or "",
            conversation_id=run.dify_conversation_id,
            task_id=run.dify_task_id,
            message_id=None,
            prompt_tokens=run.prompt_tokens,
            completion_tokens=run.completion_tokens,
            total_price=run.cost_amount,
            currency=run.cost_currency,
            latency_ms=run.latency_ms,
            citations=run.citations or [],
        )
        return self._response(
            run,
            output_message,
            conversation_public_id,
            result,
            duplicate=True,
        )

    @staticmethod
    def _response(
        run: AiAgentRun,
        message: Message,
        conversation_public_id: str,
        result: DifyChatResult,
        *,
        duplicate: bool = False,
    ) -> AgentChatResponse:
        return AgentChatResponse(
            run_id=run.public_id,
            conversation_id=conversation_public_id,
            message_id=message.public_id,
            answer=result.answer,
            dify_conversation_id=result.conversation_id,
            citations=result.citations,
            usage=AgentUsage(
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                cost_amount=result.total_price,
                cost_currency=result.currency,
                latency_ms=result.latency_ms,
            ),
            duplicate=duplicate,
        )
