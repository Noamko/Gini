from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ExecutionLogResponse(BaseModel):
    id: UUID
    trace_id: str
    conversation_id: UUID | None
    agent_id: UUID | None
    agent_name: str | None
    step_type: str
    step_name: str | None
    step_order: int
    input_data: dict | None
    output_data: dict | None
    error: str | None
    duration_ms: float
    input_tokens: int
    output_tokens: int
    cost_usd: float
    model: str | None
    metadata: dict
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_model(cls, log) -> "ExecutionLogResponse":
        return cls(
            id=log.id,
            trace_id=log.trace_id,
            conversation_id=log.conversation_id,
            agent_id=log.agent_id,
            agent_name=log.agent_name,
            step_type=log.step_type,
            step_name=log.step_name,
            step_order=log.step_order,
            input_data=log.input_data,
            output_data=log.output_data,
            error=log.error,
            duration_ms=log.duration_ms,
            input_tokens=log.input_tokens,
            output_tokens=log.output_tokens,
            cost_usd=log.cost_usd,
            model=log.model,
            metadata=log.metadata_,
            created_at=log.created_at,
        )


class TraceSummary(BaseModel):
    trace_id: str
    conversation_id: UUID | None
    agent_name: str | None
    step_count: int
    total_duration_ms: float
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float
    started_at: datetime
    step_types: list[str]
