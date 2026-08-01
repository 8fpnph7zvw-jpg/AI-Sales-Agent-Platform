from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.api.dependencies.auth import Principal, get_current_principal
from app.core.exceptions import ResourceNotFoundError
from app.main import create_app
from app.modules.conversation.repository import ConversationRepository
from app.modules.conversation.router import get_conversation_service
from app.modules.conversation.schemas import ConversationDeleteResponse
from app.modules.conversation.service import ConversationService


def principal() -> Principal:
    return Principal(
        user_id=11,
        user_public_id="01ARZ3NDEKTSV4RRFFQ69G5FA1",
        tenant_id=3,
        tenant_public_id="01ARZ3NDEKTSV4RRFFQ69G5FA2",
        permissions=frozenset({"conversation.read_all"}),
    )


@pytest.mark.asyncio
async def test_service_deletes_conversation_and_commits() -> None:
    session = AsyncMock()
    repository = AsyncMock()
    conversation = SimpleNamespace(id=7, tenant_id=3)
    repository.get_by_id_or_public_id.return_value = conversation
    service = ConversationService(session, repository)

    result = await service.delete(principal(), "7")

    repository.get_by_id_or_public_id.assert_awaited_once_with(
        3,
        "7",
        for_update=True,
        assigned_user_id=None,
    )
    repository.delete.assert_awaited_once_with(conversation)
    session.commit.assert_awaited_once_with()
    assert result == ConversationDeleteResponse(
        success=True,
        message="conversation deleted",
    )


@pytest.mark.asyncio
async def test_service_returns_not_found_without_committing() -> None:
    session = AsyncMock()
    repository = AsyncMock()
    repository.get_by_id_or_public_id.return_value = None
    service = ConversationService(session, repository)

    with pytest.raises(ResourceNotFoundError):
        await service.delete(principal(), "01KYXPEMAFYW72GM0E31WR5NRV")

    repository.delete.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("identifier", "expected_fragment"),
    [
        ("7", "conversations.id = 7"),
        (
            "01KYXPEMAFYW72GM0E31WR5NRV",
            "conversations.public_id = '01KYXPEMAFYW72GM0E31WR5NRV'",
        ),
    ],
)
async def test_repository_selects_numeric_id_or_public_id(
    identifier: str,
    expected_fragment: str,
) -> None:
    session = AsyncMock()
    session.scalar.return_value = None
    repository = ConversationRepository(session)

    await repository.get_by_id_or_public_id(3, identifier, for_update=True)

    statement = session.scalar.await_args.args[0]
    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "conversations.tenant_id = 3" in sql
    assert expected_fragment in sql
    assert "FOR UPDATE" in sql


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "identifier",
    ["7", "01KYXPEMAFYW72GM0E31WR5NRV"],
)
async def test_delete_endpoint_accepts_numeric_and_public_ids(identifier: str) -> None:
    app = create_app()
    received: list[str] = []

    class FakeConversationService:
        async def delete(
            self,
            request_principal: Principal,
            conversation_id: str,
        ) -> ConversationDeleteResponse:
            assert request_principal.tenant_id == 3
            received.append(conversation_id)
            return ConversationDeleteResponse()

    async def principal_override() -> Principal:
        return principal()

    async def service_override() -> FakeConversationService:
        return FakeConversationService()

    app.dependency_overrides[get_current_principal] = principal_override
    app.dependency_overrides[get_conversation_service] = service_override
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.delete(f"/api/v1/conversations/{identifier}")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "message": "conversation deleted",
    }
    assert received == [identifier]


@pytest.mark.asyncio
async def test_delete_endpoint_returns_404_for_missing_conversation() -> None:
    app = create_app()

    class FakeConversationService:
        async def delete(self, request_principal: Principal, conversation_id: str) -> None:
            del request_principal, conversation_id
            raise ResourceNotFoundError("Conversation")

    async def principal_override() -> Principal:
        return principal()

    async def service_override() -> FakeConversationService:
        return FakeConversationService()

    app.dependency_overrides[get_current_principal] = principal_override
    app.dependency_overrides[get_conversation_service] = service_override
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.delete(
            "/api/v1/conversations/01KYXPEMAFYW72GM0E31WR5NRV"
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
