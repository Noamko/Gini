from pydantic import BaseModel

from app.schemas.common import IDTimestampMixin


class ToolCreate(BaseModel):
    name: str
    description: str
    parameters_schema: dict = {"type": "object", "properties": {}}
    code: str
    requires_sandbox: bool = False
    requires_approval: bool = False


class ToolUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    parameters_schema: dict | None = None
    code: str | None = None
    requires_approval: bool | None = None
    requires_sandbox: bool | None = None
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
    code: str | None = None

    model_config = {"from_attributes": True}
