"""Pydantic schemas for skills."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class SkillCreate(BaseModel):
    name: str
    description: str | None = None
    instructions: str = ""
    tool_ids: list[UUID] = []
    credential_ids: list[UUID] = []


class SkillUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    instructions: str | None = None
    is_active: bool | None = None
    tool_ids: list[UUID] | None = None
    credential_ids: list[UUID] | None = None


class SkillToolResponse(BaseModel):
    id: UUID
    name: str
    description: str

    model_config = {"from_attributes": True}


class SkillCredentialResponse(BaseModel):
    id: UUID
    name: str
    credential_type: str

    model_config = {"from_attributes": True}


class SkillResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    instructions: str
    is_active: bool
    tools: list[SkillToolResponse] = []
    credentials: list[SkillCredentialResponse] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
