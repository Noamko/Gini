"""Meta-tool: list existing agents so an agent can discover ids/names."""

from typing import Any

import structlog
from fastapi import HTTPException

from app.dependencies import async_session
from app.tools.base import BaseTool, ToolResult

logger = structlog.get_logger("list_agents")


class ListAgentsTool(BaseTool):
    name = "list_agents"
    description = (
        "List the agents that exist on the platform, with their ids, names, and descriptions. "
        "Use this to find the agent_id values needed for create_workflow steps or create_webhook targets, "
        "or to check whether an agent already exists before creating one."
    )
    requires_sandbox = False
    requires_approval = False
    default_catalog = False
    parameters_schema = {
        "type": "object",
        "properties": {},
    }

    async def execute(self, *, caller_agent_id: str | None = None, **kwargs: Any) -> ToolResult:
        from app.api.agents import list_agents as list_agents_endpoint

        try:
            async with async_session() as db:
                result = await list_agents_endpoint(offset=0, limit=200, db=db)
        except HTTPException as e:
            return ToolResult(success=False, error=f"{e.status_code}: {e.detail}")
        except Exception as e:
            await logger.aerror("list_agents_failed", error=str(e))
            return ToolResult(success=False, error=f"list_agents failed: {e}")

        items = result.get("items", [])
        if not items:
            return ToolResult(output="No agents exist yet.", metadata={"count": 0})

        lines = []
        for a in items:
            tag = " [main]" if a.is_main else ""
            desc = f" — {a.description}" if a.description else ""
            lines.append(f"- {a.name}{tag} (id={a.id}){desc}")
        return ToolResult(
            output="Agents:\n" + "\n".join(lines),
            metadata={"count": len(items)},
        )
