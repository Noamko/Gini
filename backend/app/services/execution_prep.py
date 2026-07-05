"""Preparation helpers for execution-ready prompts and tool metadata."""

from dataclasses import dataclass, field

from app.models.agent import Agent
from app.services.grant_resolver import (
    PooledCredential,
    get_agent_credential_pool,
    get_agent_tool_grants,
)
from app.services.skill_executor import (
    get_agent_skill_tool_names,
    get_assembled_prompt,
    get_autonomous_prompt,
)
from app.services.tool_catalog import ToolPolicy, list_tool_policies


@dataclass
class ExecutionResources:
    system_prompt: str
    tool_policies: list[ToolPolicy]
    tool_policy_by_name: dict[str, ToolPolicy]
    tool_specs: list[dict]
    # tool_name -> {slot_name: credential_id | [credential_id, ...]}; only the bound slots reach each tool.
    tool_slot_bindings: dict[str, dict[str, str | list[str]]] = field(default_factory=dict)
    # credential_id -> decrypted credential (the agent's pool: direct + skill-bundled).
    credential_pool: dict[str, PooledCredential] = field(default_factory=dict)


def _agent_role(agent: Agent) -> str:
    metadata = getattr(agent, "metadata_", None) or {}
    return str(metadata.get("role", "")).strip().lower()


async def _tool_grants_for_agent(agent: Agent) -> tuple[set[str] | None, set[str]]:
    """Resolve an agent's tool grants as ``(allowed_default_names | None, optin_names)``.

    Effective tools are the union of the agent's direct tool grants and the tools bundled by its
    assigned skills. ``allowed_default_names`` restricts the default catalog (None = full catalog);
    dispatchers and agents with no default-catalog grants keep the full catalog. ``optin_names`` are
    opt-in tools (``default_catalog=False``, e.g. agent-management tools) granted directly or via a
    skill; these are additive and never strip the default catalog.
    """
    from app.tools.registry import get_tool

    agent_id = getattr(agent, "id", None)
    if agent_id is None:
        return None, set()

    skill_names = await get_agent_skill_tool_names(agent_id)
    direct_names = set((await get_agent_tool_grants(agent_id)).keys())
    granted = skill_names | direct_names

    optin = {
        name for name in granted if (tool := get_tool(name)) is not None and not getattr(tool, "default_catalog", True)
    }
    default_names = granted - optin

    if _agent_role(agent) == "dispatcher" or not default_names:
        return None, optin
    return default_names, optin


async def prepare_chat_resources(agent: Agent) -> ExecutionResources:
    """Build prompt and tool metadata for interactive chat."""
    system_prompt = await get_assembled_prompt(agent)
    allowed_tool_names, optin_tool_names = await _tool_grants_for_agent(agent)
    tool_slot_bindings = await get_agent_tool_grants(agent.id)
    credential_pool = await get_agent_credential_pool(agent.id)
    tool_policies = await list_tool_policies(
        include_approval_tools=True,
        allowed_tool_names=allowed_tool_names,
        optin_tool_names=optin_tool_names,
    )
    return ExecutionResources(
        system_prompt=system_prompt,
        tool_policies=tool_policies,
        tool_policy_by_name={policy.name: policy for policy in tool_policies},
        tool_specs=[policy.to_llm_spec() for policy in tool_policies],
        tool_slot_bindings=tool_slot_bindings,
        credential_pool=credential_pool,
    )


async def prepare_autonomous_resources(
    agent: Agent,
    *,
    include_approval_tools: bool | None = None,
) -> ExecutionResources:
    """Build prompt and tool metadata for autonomous execution."""
    system_prompt = await get_autonomous_prompt(agent)
    allowed_tool_names, optin_tool_names = await _tool_grants_for_agent(agent)
    tool_slot_bindings = await get_agent_tool_grants(agent.id)
    credential_pool = await get_agent_credential_pool(agent.id)
    effective_include_approval_tools = agent.auto_approve if include_approval_tools is None else include_approval_tools
    tool_policies = await list_tool_policies(
        include_approval_tools=effective_include_approval_tools,
        allowed_tool_names=allowed_tool_names,
        optin_tool_names=optin_tool_names,
    )
    return ExecutionResources(
        system_prompt=system_prompt,
        tool_policies=tool_policies,
        tool_policy_by_name={policy.name: policy for policy in tool_policies},
        tool_specs=[policy.to_llm_spec() for policy in tool_policies],
        tool_slot_bindings=tool_slot_bindings,
        credential_pool=credential_pool,
    )
