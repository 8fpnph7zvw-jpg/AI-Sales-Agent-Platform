from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import Principal, require_any_permission
from app.core.config import get_settings
from app.db.session import get_db
from app.integrations.dify.client import DifyClient
from app.modules.ai_agent.repository import AiAgentRepository
from app.modules.ai_agent.schemas import AgentChatRequest, AgentChatResponse
from app.modules.ai_agent.service import AiAgentService

router = APIRouter(prefix="/agent", tags=["AI Agent"])


def get_ai_agent_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AiAgentService:
    return AiAgentService(
        session,
        AiAgentRepository(session),
        DifyClient(get_settings()),
    )


@router.post("/chat", response_model=AgentChatResponse)
async def agent_chat(
    payload: AgentChatRequest,
    request: Request,
    service: Annotated[AiAgentService, Depends(get_ai_agent_service)],
    principal: Annotated[
        Principal,
        Depends(require_any_permission("ai_agent.chat")),
    ],
) -> AgentChatResponse:
    return await service.chat(
        principal,
        payload,
        request_id=request.headers.get("X-Request-ID"),
    )
