from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import IDTimestampMixin


class ConversationCreate(BaseModel):
    title: str | None = None
    agent_id: UUID | None = None
    metadata: dict = {}


class ConversationResponse(IDTimestampMixin):
    title: str | None
    agent_id: UUID | None
    metadata: dict

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_model(cls, conv) -> "ConversationResponse":
        return cls(
            id=conv.id,
            title=conv.title,
            agent_id=conv.agent_id,
            metadata=conv.metadata_,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
        )
