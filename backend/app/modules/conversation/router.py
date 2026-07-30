from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import Principal, require_any_permission
from app.core.config import get_settings
from app.core.encryption import ConfigCipher
from app.db.session import get_db
from app.modules.conversation.repository import ConversationRepository
from app.modules.conversation.schemas import (
    ConversationCreate,
    ConversationListResponse,
    ConversationMessageCreate,
    ConversationMessageListResponse,
    ConversationMessageResponse,
    ConversationRead,
)
from app.modules.conversation.service import ConversationService

router = APIRouter(prefix="/conversation", tags=["Conversation"])
management_router = APIRouter(prefix="/conversations", tags=["Conversation"])


def get_conversation_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ConversationService:
    settings = get_settings()
    return ConversationService(
        session,
        ConversationRepository(session),
        settings,
        ConfigCipher(settings),
    )


@management_router.post("", response_model=ConversationRead, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    payload: ConversationCreate,
    service: Annotated[ConversationService, Depends(get_conversation_service)],
    principal: Annotated[
        Principal,
        Depends(require_any_permission("ai_agent.chat", "conversation.ai_manage")),
    ],
) -> ConversationRead:
    return await service.create(principal, payload)


@management_router.get("", response_model=ConversationListResponse)
async def list_conversations(
    service: Annotated[ConversationService, Depends(get_conversation_service)],
    principal: Annotated[
        Principal,
        Depends(
            require_any_permission(
                "conversation.read_own",
                "conversation.read_team",
                "conversation.read_all",
            )
        ),
    ],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    status_filter: Annotated[str | None, Query(alias="status", max_length=24)] = None,
    search: Annotated[str | None, Query(max_length=160)] = None,
) -> ConversationListResponse:
    return await service.list(
        principal,
        limit=limit,
        offset=offset,
        status=status_filter,
        search=search,
    )


@management_router.get(
    "/{conversation_id}/messages",
    response_model=ConversationMessageListResponse,
)
async def list_conversation_messages(
    conversation_id: str,
    service: Annotated[ConversationService, Depends(get_conversation_service)],
    principal: Annotated[
        Principal,
        Depends(
            require_any_permission(
                "conversation.read_own",
                "conversation.read_team",
                "conversation.read_all",
            )
        ),
    ],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    before_sequence: Annotated[int | None, Query(ge=1)] = None,
) -> ConversationMessageListResponse:
    return await service.list_messages(
        principal,
        conversation_id,
        limit=limit,
        before_sequence=before_sequence,
    )


@router.post(
    "/message",
    response_model=ConversationMessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def send_message(
    payload: ConversationMessageCreate,
    service: Annotated[ConversationService, Depends(get_conversation_service)],
    principal: Annotated[
        Principal,
        Depends(require_any_permission("message.send")),
    ],
) -> ConversationMessageResponse:
    return await service.send_message(principal, payload)
