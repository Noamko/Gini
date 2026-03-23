from datetime import datetime
from uuid import UUID
from pydantic import BaseModel


class MemoryCreate(BaseModel):
    content: str
    agent_id: UUID | None = None
    source: str = "manual"
    source_id: str | None = None
    metadata: dict = {}


class MemoryResponse(BaseModel):
    id: UUID
    agent_id: UUID | None
    content: str
    summary: str | None
    source: str
    source_id: str | None
    metadata: dict
    similarity: float | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
