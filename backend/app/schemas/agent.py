from uuid import UUID

from pydantic import BaseModel, model_validator

from app.config import default_model_for_provider
from app.schemas.common import IDTimestampMixin


class ToolGrant(BaseModel):
    tool_name: str
    # slot_name -> credential id(s) to bind for that slot. A single slot maps to one id;
    # a ``multi`` slot maps to a list of ids (broadcast to all bound credentials).
    slot_bindings: dict[str, UUID | list[UUID]] = {}


class AgentCreate(BaseModel):
    name: str
    description: str | None = None
    system_prompt: str
    llm_provider: str = "openai"
    llm_model: str = "gpt-5.5"
    temperature: float = 0.7
    max_tokens: int = 4096
    is_main: bool = False

    auto_approve: bool = False
    daily_budget_usd: float | None = None
    metadata: dict = {}
    # Direct grants applied at creation (atomic). Skills remain optional bundles.
    tool_grants: list[ToolGrant] = []
    credential_ids: list[UUID] = []
    skill_ids: list[UUID] = []

    @model_validator(mode="before")
    @classmethod
    def _fill_model_for_provider(cls, data):
        # If a provider is given without an explicit model, use that provider's default model
        # so we never get a mismatch (e.g. provider=openai with a claude-* model).
        if isinstance(data, dict):
            provider = data.get("llm_provider")
            if provider and not data.get("llm_model"):
                data = {**data, "llm_model": default_model_for_provider(provider)}
        return data


class AgentUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    is_active: bool | None = None

    auto_approve: bool | None = None
    daily_budget_usd: float | None = None
    metadata: dict | None = None
    # Provided fields are synced (full-replace); omitted fields are left untouched.
    tool_grants: list[ToolGrant] | None = None
    credential_ids: list[UUID] | None = None
    skill_ids: list[UUID] | None = None

    @model_validator(mode="before")
    @classmethod
    def _fill_model_for_provider(cls, data):
        # Changing provider without specifying a model snaps the model to that provider's default.
        if isinstance(data, dict):
            provider = data.get("llm_provider")
            if provider and not data.get("llm_model"):
                data = {**data, "llm_model": default_model_for_provider(provider)}
        return data


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

    auto_approve: bool
    daily_budget_usd: float | None
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
            auto_approve=agent.auto_approve,
            daily_budget_usd=agent.daily_budget_usd,
            metadata=agent.metadata_,
            created_at=agent.created_at,
            updated_at=agent.updated_at,
        )
