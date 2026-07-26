from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import Principal, require_any_permission
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.db.session import get_db
from app.modules.knowledge.repository import KnowledgeRepository
from app.modules.knowledge.schemas import (
    KnowledgeDocumentList,
    KnowledgeDocumentRead,
    RetrievalRequest,
    RetrievalResponse,
)
from app.modules.knowledge.service import RagService

router = APIRouter(prefix="/knowledge", tags=["Knowledge / RAG"])


def get_rag_service(session: Annotated[AsyncSession, Depends(get_db)]) -> RagService:
    return RagService(KnowledgeRepository(session), get_settings())


@router.get("/files", response_model=KnowledgeDocumentList)
async def list_documents(
    service: Annotated[RagService, Depends(get_rag_service)],
    principal: Annotated[
        Principal, Depends(require_any_permission("knowledge.read", "knowledge.manage"))
    ],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    search: Annotated[str | None, Query(max_length=255)] = None,
) -> KnowledgeDocumentList:
    rows, total = await service.repository.list_documents(
        principal.tenant_id, limit=limit, offset=offset, search=search
    )
    return KnowledgeDocumentList(
        data=[
            KnowledgeDocumentRead(
                public_id=document.public_id,
                filename=document.filename,
                collection_name=collection_name,
                status=document.status,
                chunk_count=document.chunk_count,
                size_bytes=document.size_bytes,
                error_message=document.error_message,
                updated_at=document.updated_at,
            )
            for document, collection_name in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/files", response_model=KnowledgeDocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document(
    request: Request,
    service: Annotated[RagService, Depends(get_rag_service)],
    principal: Annotated[
        Principal, Depends(require_any_permission("knowledge.upload", "knowledge.manage"))
    ],
) -> KnowledgeDocumentRead:
    form = await request.form()
    file = form.get("file")
    if not isinstance(file, UploadFile):
        raise AppError(422, "DOCUMENT_REQUIRED", "Multipart field 'file' is required.")
    collection_value = form.get("collection_id")
    collection_id = str(collection_value) if collection_value else None
    document = await service.upload(
        principal,
        file.filename or "document",
        file.content_type or "application/octet-stream",
        await file.read(),
        collection_id,
    )
    collection = await service.repository.get_collection(principal.tenant_id, collection_id)
    return KnowledgeDocumentRead(
        public_id=document.public_id,
        filename=document.filename,
        collection_name=collection.name if collection else "Default",
        status=document.status,
        chunk_count=document.chunk_count,
        size_bytes=document.size_bytes,
        error_message=document.error_message,
        updated_at=document.updated_at,
    )


@router.post("/retrieve", response_model=RetrievalResponse)
async def retrieve(
    payload: RetrievalRequest,
    service: Annotated[RagService, Depends(get_rag_service)],
    principal: Annotated[
        Principal, Depends(require_any_permission("knowledge.read", "knowledge.manage"))
    ],
) -> RetrievalResponse:
    return await service.retrieve(
        principal, payload.query, payload.collection_id, payload.top_k, payload.min_score
    )
