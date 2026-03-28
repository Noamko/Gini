from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ScheduleCreate(BaseModel):
    agent_id: UUID | None = None
    workflow_id: UUID | None = None
    name: str
    cron_expression: str
    instructions: str | None = None
    enabled: bool = True


class ScheduleUpdate(BaseModel):
    name: str | None = None
    cron_expression: str | None = None
    instructions: str | None = None
    enabled: bool | None = None


class ScheduleResponse(BaseModel):
    id: UUID
    agent_id: UUID | None
    agent_name: str | None
    workflow_id: UUID | None
    workflow_name: str | None
    name: str
    cron_expression: str
    instructions: str | None
    enabled: bool
    last_run_at: datetime | None
    next_run_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_model(cls, schedule) -> "ScheduleResponse":
        return cls(
            id=schedule.id,
            agent_id=schedule.agent_id,
            agent_name=schedule.agent.name if schedule.agent else None,
            workflow_id=schedule.workflow_id,
            workflow_name=schedule.workflow.name if schedule.workflow else None,
            name=schedule.name,
            cron_expression=schedule.cron_expression,
            instructions=schedule.instructions,
            enabled=schedule.enabled,
            last_run_at=schedule.last_run_at,
            next_run_at=schedule.next_run_at,
            created_at=schedule.created_at,
            updated_at=schedule.updated_at,
        )
