from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import Principal, require_any_permission
from app.db.session import get_db
from app.modules.conversation.repository import ConversationRepository
from app.modules.conversation.schemas import (
    ConversationMessageCreate,
    ConversationMessageResponse,
)
from app.modules.conversation.service import ConversationService

router = APIRouter(prefix="/conversation", tags=["Conversation"])


def get_conversation_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ConversationService:
    return ConversationService(session, ConversationRepository(session))


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
