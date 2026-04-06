"""Preparation helpers for execution-ready prompts and tool metadata."""
from dataclasses import dataclass

from app.models.agent import Agent
from app.services.skill_executor import (
    get_assembled_prompt,
    get_agent_credentials,
    get_agent_skill_tool_names,
    get_autonomous_prompt,
)
from app.services.tool_catalog import ToolPolicy, list_tool_policies


@dataclass
class ExecutionResources:
    system_prompt: str
    tool_policies: list[ToolPolicy]
    tool_policy_by_name: dict[str, ToolPolicy]
    tool_specs: list[dict]
    credentials: dict[str, str]


def _agent_role(agent: Agent) -> str:
    metadata = getattr(agent, "metadata_", None) or {}
    return str(metadata.get("role", "")).strip().lower()


async def _allowed_tool_names_for_agent(agent: Agent) -> set[str] | None:
    """Restrict specialist agents to tools linked by their active skills.

    Dispatchers keep the full tool catalog because their job is routing, not
    specialization. Specialists without linked skill tools also keep the
    current broad catalog until they are modeled more precisely.
    """
    if _agent_role(agent) == "dispatcher":
        return None

    agent_id = getattr(agent, "id", None)
    if not agent_id:
        return None

    allowed_tool_names = await get_agent_skill_tool_names(agent_id)
    return allowed_tool_names or None


async def prepare_chat_resources(agent: Agent) -> ExecutionResources:
    """Build prompt and tool metadata for interactive chat."""
    system_prompt = await get_assembled_prompt(agent)
    allowed_tool_names = await _allowed_tool_names_for_agent(agent)
    credentials = await get_agent_credentials(agent.id)
    tool_policies = await list_tool_policies(
        include_approval_tools=True,
        allowed_tool_names=allowed_tool_names,
    )
    return ExecutionResources(
        system_prompt=system_prompt,
        tool_policies=tool_policies,
        tool_policy_by_name={policy.name: policy for policy in tool_policies},
        tool_specs=[policy.to_llm_spec() for policy in tool_policies],
        credentials=credentials,
    )


async def prepare_autonomous_resources(
    agent: Agent,
    *,
    include_approval_tools: bool | None = None,
) -> ExecutionResources:
    """Build prompt and tool metadata for autonomous execution."""
    system_prompt = await get_autonomous_prompt(agent)
    allowed_tool_names = await _allowed_tool_names_for_agent(agent)
    credentials = await get_agent_credentials(agent.id)
    effective_include_approval_tools = agent.auto_approve if include_approval_tools is None else include_approval_tools
    tool_policies = await list_tool_policies(
        include_approval_tools=effective_include_approval_tools,
        allowed_tool_names=allowed_tool_names,
    )
    return ExecutionResources(
        system_prompt=system_prompt,
        tool_policies=tool_policies,
        tool_policy_by_name={policy.name: policy for policy in tool_policies},
        tool_specs=[policy.to_llm_spec() for policy in tool_policies],
        credentials=credentials,
    )
