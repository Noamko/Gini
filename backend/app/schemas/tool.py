from pydantic import BaseModel

from app.schemas.common import IDTimestampMixin


class ToolUpdate(BaseModel):
    requires_approval: bool | None = None
    is_active: bool | None = None


class ToolResponse(IDTimestampMixin):
    name: str
    description: str
    parameters_schema: dict
    implementation: str
    requires_sandbox: bool
    requires_approval: bool
    is_builtin: bool
    is_active: bool

    model_config = {"from_attributes": True}
