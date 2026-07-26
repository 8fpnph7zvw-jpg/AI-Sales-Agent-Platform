from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from app.api.dependencies.auth import Principal
from app.core.config import Settings
from app.core.exceptions import AppError, ResourceNotFoundError
from app.models.rag.embedding import Embedding
from app.models.rag.knowledge_chunk import KnowledgeChunk
from app.models.rag.knowledge_collection import KnowledgeCollection
from app.models.rag.knowledge_document import KnowledgeDocument
from app.modules.knowledge.embedding import EmbeddingService
from app.modules.knowledge.parser import DocumentParser
from app.modules.knowledge.repository import KnowledgeRepository
from app.modules.knowledge.schemas import RetrievalHit, RetrievalResponse
from app.modules.knowledge.vector_store import ChromaVectorStore


class RagService:
    def __init__(self, repository: KnowledgeRepository, settings: Settings) -> None:
        self.repository = repository
        self.session = repository.session
        self.settings = settings
        self.parser = DocumentParser()
        self.embedder = EmbeddingService(settings.rag_embedding_dimensions)
        self.vector_store = ChromaVectorStore(
            settings.chroma_url, settings.chroma_collection, settings.chroma_enabled
        )

    def split_text(self, text: str) -> list[str]:
        size, overlap = self.settings.rag_chunk_size, self.settings.rag_chunk_overlap
        if size <= overlap:
            raise RuntimeError("RAG_CHUNK_SIZE must be larger than RAG_CHUNK_OVERLAP")
        return [
            text[start : start + size].strip()
            for start in range(0, len(text), size - overlap)
            if text[start : start + size].strip()
        ]

    async def upload(
        self,
        principal: Principal,
        filename: str,
        mime_type: str,
        content: bytes,
        collection_public_id: str | None,
    ) -> KnowledgeDocument:
        if not content or len(content) > self.settings.rag_max_upload_bytes:
            raise AppError(
                413,
                "DOCUMENT_SIZE_INVALID",
                f"Document must be between 1 and {self.settings.rag_max_upload_bytes} bytes.",
            )
        collection = await self.repository.get_collection(principal.tenant_id, collection_public_id)
        if collection is None and collection_public_id:
            raise ResourceNotFoundError("Knowledge collection")
        if collection is None:
            collection = KnowledgeCollection(
                tenant_id=principal.tenant_id,
                name="Default",
                description="Default RAG collection",
                embedding_provider=self.embedder.model,
                created_by=principal.user_id,
            )
            self.session.add(collection)
            await self.session.flush()
        document = KnowledgeDocument(
            tenant_id=principal.tenant_id,
            collection_id=collection.id,
            filename=filename,
            mime_type=mime_type or "application/octet-stream",
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            uploaded_by=principal.user_id,
        )
        self.session.add(document)
        await self.session.flush()
        try:
            chunks = self.split_text(self.parser.parse(filename, content))
            vectors: list[list[float]] = []
            models: list[KnowledgeChunk] = []
            for index, chunk_text in enumerate(chunks):
                chunk = KnowledgeChunk(
                    tenant_id=principal.tenant_id,
                    document_id=document.id,
                    chunk_index=index,
                    content_text=chunk_text,
                    content_hash=hashlib.sha256(chunk_text.encode()).hexdigest(),
                    token_count=len(chunk_text.split()),
                    metadata_json={"filename": filename},
                    sync_status="ready",
                )
                self.session.add(chunk)
                await self.session.flush()
                vector = self.embedder.embed(chunk_text)
                vectors.append(vector)
                models.append(chunk)
                self.session.add(
                    Embedding(
                        tenant_id=principal.tenant_id,
                        chunk_id=chunk.id,
                        model=self.embedder.model,
                        dimensions=len(vector),
                        vector=vector,
                        vector_metadata={"document_id": document.public_id},
                    )
                )
            document.status, document.chunk_count, document.processed_at = (
                "ready",
                len(models),
                datetime.now(UTC),
            )
            await self.session.commit()
            try:
                await self.vector_store.upsert(
                    ids=[item.public_id for item in models],
                    embeddings=vectors,
                    documents=[item.content_text for item in models],
                    metadatas=[
                        {"tenant_id": principal.tenant_public_id, "document_id": document.public_id}
                        for item in models
                    ],
                )
            except Exception:
                # MySQL vectors keep retrieval available if Chroma is temporarily unavailable.
                pass
            return document
        except Exception as exc:
            await self.session.rollback()
            raise exc

    async def retrieve(
        self,
        principal: Principal,
        query: str,
        collection_public_id: str | None,
        top_k: int,
        min_score: float,
    ) -> RetrievalResponse:
        collection = (
            await self.repository.get_collection(principal.tenant_id, collection_public_id)
            if collection_public_id
            else None
        )
        if collection_public_id and collection is None:
            raise ResourceNotFoundError("Knowledge collection")
        query_vector = self.embedder.embed(query)
        scored = [
            (self.embedder.similarity(query_vector, embedding.vector), chunk, document)
            for chunk, document, embedding in await self.repository.candidates(
                principal.tenant_id, collection.id if collection else None
            )
        ]
        scored.sort(key=lambda item: item[0], reverse=True)
        hits = [
            RetrievalHit(
                chunk_id=chunk.public_id,
                document_id=document.public_id,
                filename=document.filename,
                content=chunk.content_text,
                score=round(score, 6),
                chunk_index=chunk.chunk_index,
            )
            for score, chunk, document in scored[:top_k]
            if score >= min_score
        ]
        return RetrievalResponse(
            query=query,
            hits=hits,
            context="\n\n".join(f"[Source: {hit.filename}]\n{hit.content}" for hit in hits),
        )
