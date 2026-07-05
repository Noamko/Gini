"""Meta-tool: let an agent create a new specialist agent."""

from typing import Any

import structlog
from fastapi import HTTPException

from app.dependencies import async_session
from app.tools.base import BaseTool, ToolResult

logger = structlog.get_logger("create_agent")


class CreateAgentTool(BaseTool):
    name = "create_agent"
    description = (
        "Create a new specialist agent. Use this to spin up a focused sub-agent that can later be "
        "delegated to (via delegate_task), chained in a workflow, or triggered by a webhook. "
        "Provide a clear, single-purpose system prompt. The new agent starts with the default tool "
        "catalog only (it will NOT inherit agent-management tools). Returns the new agent's id."
    )
    requires_sandbox = False
    requires_approval = True
    default_catalog = False
    parameters_schema = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Unique, human-readable name for the agent (e.g. 'Market Researcher').",
            },
            "system_prompt": {
                "type": "string",
                "description": "The agent's system prompt — define its role, scope, and behavior precisely.",
            },
            "description": {
                "type": "string",
                "description": "Short description of what the agent is for.",
            },
            "llm_provider": {
                "type": "string",
                "description": "LLM provider: 'openai' (default) or 'anthropic'.",
            },
            "llm_model": {
                "type": "string",
                "description": (
                    "Exact model id, which MUST belong to llm_provider (e.g. 'gpt-5.5' for openai, "
                    "'claude-sonnet-4-6' for anthropic). If omitted, the provider's default model is used."
                ),
            },
            "temperature": {
                "type": "number",
                "description": "Sampling temperature 0.0-1.0. Defaults to 0.7.",
            },
            "max_tokens": {
                "type": "integer",
                "description": "Max output tokens per call. Defaults to 4096.",
            },
            "auto_approve": {
                "type": "boolean",
                "description": "If true the agent runs tools without human approval. Leave false unless asked.",
            },
            "daily_budget_usd": {
                "type": "number",
                "description": "Optional daily spend cap in USD.",
            },
        },
        "required": ["name", "system_prompt"],
    }

    async def execute(self, *, caller_agent_id: str | None = None, **kwargs: Any) -> ToolResult:
        from app.api.agents import create_agent as create_agent_endpoint
        from app.schemas.agent import AgentCreate

        # Never let the LLM mint a second main agent.
        kwargs.pop("is_main", None)
        kwargs.pop("credential_values", None)
        params = {k: v for k, v in kwargs.items() if v is not None}

        try:
            body = AgentCreate(**params)
        except Exception as e:
            return ToolResult(success=False, error=f"Invalid agent parameters: {e}")

        try:
            async with async_session() as db:
                resp = await create_agent_endpoint(body, db=db)
        except HTTPException as e:
            return ToolResult(success=False, error=f"{e.status_code}: {e.detail}")
        except Exception as e:
            await logger.aerror("create_agent_failed", error=str(e))
            return ToolResult(success=False, error=f"create_agent failed: {e}")

        await logger.ainfo("agent_created", agent_id=str(resp.id), name=resp.name, by=caller_agent_id)
        return ToolResult(
            output=f"Created agent '{resp.name}' (id={resp.id}). Use this id in delegate_task, workflows, or webhooks.",
            metadata={"agent_id": str(resp.id), "agent_name": resp.name},
        )
