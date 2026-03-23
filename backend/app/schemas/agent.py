from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import IDTimestampMixin


class AgentCreate(BaseModel):
    name: str
    description: str | None = None
    system_prompt: str
    llm_provider: str = "anthropic"
    llm_model: str = "claude-sonnet-4-20250514"
    temperature: float = 0.7
    max_tokens: int = 4096
    is_main: bool = False
    use_memory: bool = False
    auto_approve: bool = False
    metadata: dict = {}


class AgentUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    is_active: bool | None = None
    use_memory: bool | None = None
    auto_approve: bool | None = None
    metadata: dict | None = None


class AgentResponse(IDTimestampMixin):
    name: str
    description: str | None
    system_prompt: str
    llm_provider: str
    llm_model: str
    temperature: float
    max_tokens: int
    state: str
    is_main: bool
    is_active: bool
    use_memory: bool
    auto_approve: bool
    metadata: dict

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_model(cls, agent) -> "AgentResponse":
        return cls(
            id=agent.id,
            name=agent.name,
            description=agent.description,
            system_prompt=agent.system_prompt,
            llm_provider=agent.llm_provider,
            llm_model=agent.llm_model,
            temperature=agent.temperature,
            max_tokens=agent.max_tokens,
            state=agent.state,
            is_main=agent.is_main,
            is_active=agent.is_active,
            use_memory=agent.use_memory,
            auto_approve=agent.auto_approve,
            metadata=agent.metadata_,
            created_at=agent.created_at,
            updated_at=agent.updated_at,
        )
