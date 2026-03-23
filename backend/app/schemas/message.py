from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import IDTimestampMixin


class MessageCreate(BaseModel):
    role: str
    content: str | None = None
    tool_calls: dict | None = None
    tool_call_id: str | None = None
    token_count: int | None = None
    model_used: str | None = None
    cost_usd: Decimal | None = None
    metadata: dict = {}


class MessageResponse(IDTimestampMixin):
    conversation_id: UUID
    role: str
    content: str | None
    tool_calls: dict | None
    tool_call_id: str | None
    token_count: int | None
    model_used: str | None
    cost_usd: Decimal | None
    metadata: dict

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_model(cls, msg) -> "MessageResponse":
        return cls(
            id=msg.id,
            conversation_id=msg.conversation_id,
            role=msg.role,
            content=msg.content,
            tool_calls=msg.tool_calls,
            tool_call_id=msg.tool_call_id,
            token_count=msg.token_count,
            model_used=msg.model_used,
            cost_usd=msg.cost_usd,
            metadata=msg.metadata_,
            created_at=msg.created_at,
            updated_at=msg.updated_at,
        )
