"""Meta-tool: let an agent author a new custom tool (Python code)."""

from typing import Any

import structlog
from fastapi import HTTPException

from app.dependencies import async_session
from app.tools.base import BaseTool, ToolResult

logger = structlog.get_logger("create_tool")


class CreateToolTool(BaseTool):
    name = "create_tool"
    description = (
        "Author a new custom tool from Python code. The code must define an async function "
        "`async def execute(**kwargs) -> dict` returning a dict with keys: success (bool), output (str), "
        "and optionally error (str) and metadata (dict). Describe the tool's inputs via parameters_schema "
        "(JSON Schema). For safety the new tool is always created sandboxed and approval-required: every "
        "execution runs in the sandbox and needs human approval. The tool is active immediately for agents "
        "whose catalog includes custom tools. Returns the new tool id."
    )
    requires_sandbox = False
    requires_approval = True
    default_catalog = False
    parameters_schema = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Unique snake_case tool name (e.g. 'fetch_weather').",
            },
            "description": {
                "type": "string",
                "description": "What the tool does and when to use it (the LLM reads this).",
            },
            "code": {
                "type": "string",
                "description": "Python source defining `async def execute(**kwargs) -> dict`.",
            },
            "parameters_schema": {
                "type": "object",
                "description": "JSON Schema for the tool's input parameters (type object with properties/required).",
            },
            "credential_slots": {
                "type": "array",
                "description": (
                    "Optional credential slots the tool needs, each an object "
                    "{name, type, required, description}. A human binds a credential to each slot; "
                    "only the bound value is injected into the tool's `credentials` at run time."
                ),
                "items": {"type": "object"},
            },
        },
        "required": ["name", "description", "code"],
    }

    async def execute(self, *, caller_agent_id: str | None = None, **kwargs: Any) -> ToolResult:
        from app.schemas.tool import ToolCreate

        kwargs.pop("credential_values", None)
        params_schema = kwargs.get("parameters_schema") or {"type": "object", "properties": {}}

        try:
            body = ToolCreate(
                name=kwargs.get("name", ""),
                description=kwargs.get("description", ""),
                parameters_schema=params_schema,
                code=kwargs.get("code", ""),
                credential_slots=kwargs.get("credential_slots") or [],
                # Safety: LLM-authored code is always sandboxed and approval-gated.
                requires_sandbox=True,
                requires_approval=True,
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Invalid tool parameters: {e}")

        from app.api.tools import create_tool as create_tool_endpoint

        try:
            async with async_session() as db:
                resp = await create_tool_endpoint(body, db=db)
        except HTTPException as e:
            return ToolResult(success=False, error=f"{e.status_code}: {e.detail}")
        except Exception as e:
            await logger.aerror("create_tool_failed", error=str(e))
            return ToolResult(success=False, error=f"create_tool failed: {e}")

        await logger.ainfo("custom_tool_created", tool_id=str(resp.id), name=resp.name, by=caller_agent_id)
        return ToolResult(
            output=(
                f"Created custom tool '{resp.name}' (id={resp.id}). It is sandboxed and approval-required — "
                f"each execution needs human approval — and is active immediately for agents whose catalog "
                f"includes custom tools."
            ),
            metadata={"tool_id": str(resp.id), "tool_name": resp.name},
        )
