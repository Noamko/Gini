"""Pydantic schemas for events."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class EventResponse(BaseModel):
    id: UUID
    event_type: str
    correlation_id: str | None = None
    conversation_id: UUID | None = None
    source: str | None = None
    payload: dict | None = None
    status: str
    result: dict | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ApprovalRequest(BaseModel):
    """Sent over WebSocket to request user approval."""
    approval_id: str
    tool_name: str
    arguments: dict
    reason: str


class ApprovalResponse(BaseModel):
    """Sent by the user to approve or reject."""
    approval_id: str
    approved: bool
    reason: str | None = None
