from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class WebhookCreate(BaseModel):
    agent_id: UUID
    name: str
    instructions_template: str | None = None
    enabled: bool = True


class WebhookUpdate(BaseModel):
    name: str | None = None
    instructions_template: str | None = None
    enabled: bool | None = None


class WebhookResponse(BaseModel):
    id: UUID
    agent_id: UUID
    agent_name: str
    name: str
    token: str
    url: str
    instructions_template: str | None
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_model(cls, webhook, base_url: str = "http://localhost:8000") -> "WebhookResponse":
        return cls(
            id=webhook.id,
            agent_id=webhook.agent_id,
            agent_name=webhook.agent.name if webhook.agent else "Unknown",
            name=webhook.name,
            token=webhook.token,
            url=f"{base_url}/api/webhooks/{webhook.token}/trigger",
            instructions_template=webhook.instructions_template,
            enabled=webhook.enabled,
            created_at=webhook.created_at,
            updated_at=webhook.updated_at,
        )
