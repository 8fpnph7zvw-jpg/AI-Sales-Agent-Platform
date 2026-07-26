from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class WorkflowRead(BaseModel):
    id: str
    name: str
    description: str | None
    status: str
    version: int
    trigger_type: str
    updated_at: datetime


class WorkflowListResponse(BaseModel):
    data: list[WorkflowRead]
    total: int
    limit: int
    offset: int
