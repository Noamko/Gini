"""delegate_task tool — allows the main agent to delegate work to sub-agents."""
from typing import Any

from app.tools.base import BaseTool, ToolResult


class DelegateTaskTool(BaseTool):
    name = "delegate_task"
    description = (
        "Delegate a task to a specialized sub-agent. "
        "Use this when a task would be better handled by a specific agent "
        "(e.g., code review, research, data analysis). "
        "The sub-agent will run autonomously and return its result."
    )
    requires_sandbox = False
    requires_approval = False
    parameters_schema = {
        "type": "object",
        "properties": {
            "agent_name": {
                "type": "string",
                "description": "The name of the agent to delegate to.",
            },
            "task": {
                "type": "string",
                "description": "A clear description of the task for the sub-agent to complete.",
            },
        },
        "required": ["agent_name", "task"],
    }

    async def execute(self, agent_name: str, task: str, **kwargs: Any) -> ToolResult:
        # Actual execution is handled by the chat layer via the orchestrator.
        # This method is a placeholder — the chat handler intercepts delegate_task calls.
        return ToolResult(
            success=False,
            error="delegate_task must be handled by the orchestrator, not executed directly.",
        )
