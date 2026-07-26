from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    public_id: str = Field(serialization_alias="id")
    filename: str
    collection_name: str
    status: str
    chunk_count: int
    size_bytes: int
    error_message: str | None
    updated_at: datetime


class KnowledgeDocumentList(BaseModel):
    data: list[KnowledgeDocumentRead]
    total: int
    limit: int
    offset: int


class RetrievalRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    collection_id: str | None = None
    top_k: int = Field(default=5, ge=1, le=20)
    min_score: float = Field(default=0.0, ge=-1, le=1)


class RetrievalHit(BaseModel):
    chunk_id: str
    document_id: str
    filename: str
    content: str
    score: float
    chunk_index: int


class RetrievalResponse(BaseModel):
    query: str
    hits: list[RetrievalHit]
    context: str
