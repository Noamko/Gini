from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class WorkflowStep(BaseModel):
    agent_id: str
    agent_name: str | None = None
    instructions: str
    pass_output: bool = True  # pass previous step's output as context


class WorkflowCreate(BaseModel):
    name: str
    description: str | None = None
    steps: list[WorkflowStep]


class WorkflowUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    enabled: bool | None = None
    steps: list[WorkflowStep] | None = None


class WorkflowResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    enabled: bool
    steps: list[dict]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_model(cls, workflow) -> "WorkflowResponse":
        return cls(
            id=workflow.id,
            name=workflow.name,
            description=workflow.description,
            enabled=workflow.enabled,
            steps=workflow.steps or [],
            created_at=workflow.created_at,
            updated_at=workflow.updated_at,
        )
