"""Pydantic schemas for credentials."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class CredentialCreate(BaseModel):
    name: str
    description: str | None = None
    credential_type: str = "api_key"
    value: str  # plaintext — will be encrypted before storage


class CredentialUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    credential_type: str | None = None
    value: str | None = None  # if provided, will re-encrypt
    is_active: bool | None = None


class CredentialResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    credential_type: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
