"""Meta-tool: let an agent create a multi-step workflow."""

from typing import Any

import structlog
from fastapi import HTTPException

from app.dependencies import async_session
from app.tools.base import BaseTool, ToolResult

logger = structlog.get_logger("create_workflow")


class CreateWorkflowTool(BaseTool):
    name = "create_workflow"
    description = (
        "Create a workflow that chains agents into a sequence of steps. Each step runs one agent with "
        "given instructions; if pass_output is true, the previous step's result is appended to the next "
        "step's instructions. Use list_agents to find agent_id values. If a step omits agent_id, the "
        "calling agent is used. Returns the new workflow id (run it via POST /api/workflows/{id}/run)."
    )
    requires_sandbox = False
    requires_approval = True
    default_catalog = False
    parameters_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Workflow name."},
            "description": {"type": "string", "description": "What the workflow does."},
            "steps": {
                "type": "array",
                "description": "Ordered steps. At least one is required.",
                "items": {
                    "type": "object",
                    "properties": {
                        "agent_id": {
                            "type": "string",
                            "description": "Agent id to run this step. Omit to use the calling agent.",
                        },
                        "instructions": {
                            "type": "string",
                            "description": "What the agent should do in this step.",
                        },
                        "pass_output": {
                            "type": "boolean",
                            "description": "Append the previous step's output to these instructions. Default true.",
                        },
                    },
                    "required": ["instructions"],
                },
            },
        },
        "required": ["name", "steps"],
    }

    async def execute(self, *, caller_agent_id: str | None = None, **kwargs: Any) -> ToolResult:
        from app.schemas.workflow import WorkflowCreate, WorkflowStep

        kwargs.pop("credential_values", None)
        raw_steps = kwargs.get("steps") or []
        if not isinstance(raw_steps, list) or not raw_steps:
            return ToolResult(success=False, error="At least one step is required.")

        steps: list[WorkflowStep] = []
        for i, step in enumerate(raw_steps):
            if not isinstance(step, dict):
                return ToolResult(success=False, error=f"Step {i + 1} is not an object.")
            agent_id = step.get("agent_id") or caller_agent_id
            if not agent_id:
                return ToolResult(
                    success=False,
                    error=f"Step {i + 1} has no agent_id and there is no calling agent to default to.",
                )
            try:
                steps.append(
                    WorkflowStep(
                        agent_id=str(agent_id),
                        instructions=step.get("instructions", ""),
                        pass_output=bool(step.get("pass_output", True)),
                    )
                )
            except Exception as e:
                return ToolResult(success=False, error=f"Invalid step {i + 1}: {e}")

        try:
            body = WorkflowCreate(name=kwargs.get("name", ""), description=kwargs.get("description"), steps=steps)
        except Exception as e:
            return ToolResult(success=False, error=f"Invalid workflow parameters: {e}")

        from app.api.workflows import create_workflow as create_workflow_endpoint

        try:
            async with async_session() as db:
                resp = await create_workflow_endpoint(body, db=db)
        except HTTPException as e:
            return ToolResult(success=False, error=f"{e.status_code}: {e.detail}")
        except Exception as e:
            await logger.aerror("create_workflow_failed", error=str(e))
            return ToolResult(success=False, error=f"create_workflow failed: {e}")

        await logger.ainfo("workflow_created", workflow_id=str(resp.id), name=resp.name, by=caller_agent_id)
        return ToolResult(
            output=f"Created workflow '{resp.name}' (id={resp.id}) with {len(resp.steps)} step(s).",
            metadata={"workflow_id": str(resp.id), "steps": len(resp.steps)},
        )
