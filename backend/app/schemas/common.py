from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class PaginatedResponse(BaseModel):
    total: int
    offset: int
    limit: int


class IDTimestampMixin(BaseModel):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
