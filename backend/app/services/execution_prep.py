"""Preparation helpers for execution-ready prompts and tool metadata."""
from dataclasses import dataclass

from app.models.agent import Agent
from app.services.skill_executor import (
    get_assembled_prompt,
    get_assembled_prompt_with_credentials,
    get_autonomous_prompt,
)
from app.services.tool_catalog import ToolPolicy, list_tool_policies


@dataclass
class ExecutionResources:
    system_prompt: str
    tool_policies: list[ToolPolicy]
    tool_policy_by_name: dict[str, ToolPolicy]
    tool_specs: list[dict]


async def prepare_chat_resources(agent: Agent) -> ExecutionResources:
    """Build prompt and tool metadata for interactive chat."""
    prompt_fn = get_assembled_prompt_with_credentials if agent.auto_approve else get_assembled_prompt
    system_prompt = await prompt_fn(agent)
    tool_policies = await list_tool_policies(include_approval_tools=True)
    return ExecutionResources(
        system_prompt=system_prompt,
        tool_policies=tool_policies,
        tool_policy_by_name={policy.name: policy for policy in tool_policies},
        tool_specs=[policy.to_llm_spec() for policy in tool_policies],
    )


async def prepare_autonomous_resources(agent: Agent) -> ExecutionResources:
    """Build prompt and tool metadata for autonomous execution."""
    system_prompt = await get_autonomous_prompt(agent)
    tool_policies = await list_tool_policies(include_approval_tools=agent.auto_approve)
    return ExecutionResources(
        system_prompt=system_prompt,
        tool_policies=tool_policies,
        tool_policy_by_name={policy.name: policy for policy in tool_policies},
        tool_specs=[policy.to_llm_spec() for policy in tool_policies],
    )
