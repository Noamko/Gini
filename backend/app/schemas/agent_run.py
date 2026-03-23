from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AgentRunCreate(BaseModel):
    agent_id: UUID
    instructions: str | None = None


class AgentRunResponse(BaseModel):
    id: UUID
    agent_id: UUID
    agent_name: str
    status: str
    instructions: str | None
    result: str | None
    error: str | None
    input_tokens: int
    output_tokens: int
    cost_usd: float
    duration_ms: float
    steps: list
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_model(cls, run) -> "AgentRunResponse":
        return cls(
            id=run.id,
            agent_id=run.agent_id,
            agent_name=run.agent.name if run.agent else "Unknown",
            status=run.status,
            instructions=run.instructions,
            result=run.result,
            error=run.error,
            input_tokens=run.input_tokens,
            output_tokens=run.output_tokens,
            cost_usd=run.cost_usd,
            duration_ms=run.duration_ms,
            steps=run.steps or [],
            created_at=run.created_at,
            updated_at=run.updated_at,
        )
