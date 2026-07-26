from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rag.embedding import Embedding
from app.models.rag.knowledge_chunk import KnowledgeChunk
from app.models.rag.knowledge_collection import KnowledgeCollection
from app.models.rag.knowledge_document import KnowledgeDocument


class KnowledgeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_collection(
        self, tenant_id: int, public_id: str | None
    ) -> KnowledgeCollection | None:
        statement = select(KnowledgeCollection).where(
            KnowledgeCollection.tenant_id == tenant_id, KnowledgeCollection.deleted_at.is_(None)
        )
        if public_id:
            statement = statement.where(KnowledgeCollection.public_id == public_id)
        else:
            statement = statement.order_by(KnowledgeCollection.id).limit(1)
        return await self.session.scalar(statement)

    async def list_documents(
        self, tenant_id: int, *, limit: int, offset: int, search: str | None
    ) -> tuple[list[tuple[KnowledgeDocument, str]], int]:
        filters = [KnowledgeDocument.tenant_id == tenant_id]
        if search:
            pattern = f"%{search.strip()}%"
            filters.append(
                or_(
                    KnowledgeDocument.filename.like(pattern), KnowledgeCollection.name.like(pattern)
                )
            )
        base = (
            select(KnowledgeDocument, KnowledgeCollection.name)
            .join(KnowledgeCollection)
            .where(*filters)
        )
        rows = list(
            (
                await self.session.execute(
                    base.order_by(KnowledgeDocument.created_at.desc()).limit(limit).offset(offset)
                )
            ).all()
        )
        total = int(
            (
                await self.session.scalar(
                    select(func.count(KnowledgeDocument.id))
                    .join(KnowledgeCollection)
                    .where(*filters)
                )
            )
            or 0
        )
        return rows, total

    async def candidates(
        self, tenant_id: int, collection_id: int | None
    ) -> list[tuple[KnowledgeChunk, KnowledgeDocument, Embedding]]:
        statement = (
            select(KnowledgeChunk, KnowledgeDocument, Embedding)
            .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .join(Embedding, Embedding.chunk_id == KnowledgeChunk.id)
            .where(KnowledgeChunk.tenant_id == tenant_id, KnowledgeDocument.status == "ready")
        )
        if collection_id is not None:
            statement = statement.where(KnowledgeDocument.collection_id == collection_id)
        return list((await self.session.execute(statement)).all())
