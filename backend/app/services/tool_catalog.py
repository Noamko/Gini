"""Centralized tool metadata and policy lookups."""
from dataclasses import dataclass

from sqlalchemy import select

from app.dependencies import async_session
from app.models.tool import Tool
from app.tools.registry import get_all_tools, get_tool


@dataclass(frozen=True)
class ToolPolicy:
    name: str
    description: str
    input_schema: dict
    requires_sandbox: bool
    requires_approval: bool
    is_builtin: bool
    is_active: bool = True

    def to_llm_spec(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


def _builtin_policy(name: str) -> ToolPolicy | None:
    tool = get_tool(name)
    if not tool:
        return None
    return ToolPolicy(
        name=tool.name,
        description=tool.description,
        input_schema=tool.parameters_schema,
        requires_sandbox=tool.requires_sandbox,
        requires_approval=tool.requires_approval,
        is_builtin=True,
        is_active=True,
    )


async def get_tool_policy(name: str) -> ToolPolicy | None:
    """Return policy metadata for a built-in or custom tool."""
    builtin = _builtin_policy(name)
    if builtin:
        return builtin

    async with async_session() as db:
        result = await db.execute(
            select(Tool).where(Tool.name == name).where(Tool.is_active == True)
        )
        tool = result.scalar_one_or_none()

    if not tool:
        return None

    return ToolPolicy(
        name=tool.name,
        description=tool.description,
        input_schema=tool.parameters_schema,
        requires_sandbox=tool.requires_sandbox,
        requires_approval=tool.requires_approval,
        is_builtin=tool.is_builtin,
        is_active=tool.is_active,
    )


async def list_tool_policies(
    *,
    include_approval_tools: bool = True,
    allowed_tool_names: set[str] | None = None,
) -> list[ToolPolicy]:
    """Return LLM-visible tools with a single policy source of truth."""
    policies: list[ToolPolicy] = []

    for tool in get_all_tools():
        policy = ToolPolicy(
            name=tool.name,
            description=tool.description,
            input_schema=tool.parameters_schema,
            requires_sandbox=tool.requires_sandbox,
            requires_approval=tool.requires_approval,
            is_builtin=True,
            is_active=True,
        )
        if allowed_tool_names is not None and policy.name not in allowed_tool_names:
            continue
        if include_approval_tools or not policy.requires_approval:
            policies.append(policy)

    async with async_session() as db:
        result = await db.execute(
            select(Tool)
            .where(Tool.is_active == True)
            .where(Tool.is_builtin == False)
            .where(Tool.code.isnot(None))
            .order_by(Tool.name)
        )
        db_tools = result.scalars().all()

    for tool in db_tools:
        policy = ToolPolicy(
            name=tool.name,
            description=tool.description,
            input_schema=tool.parameters_schema,
            requires_sandbox=tool.requires_sandbox,
            requires_approval=tool.requires_approval,
            is_builtin=False,
            is_active=tool.is_active,
        )
        if allowed_tool_names is not None and policy.name not in allowed_tool_names:
            continue
        if include_approval_tools or not policy.requires_approval:
            policies.append(policy)

    return policies


async def get_tool_specs(
    *,
    include_approval_tools: bool = True,
    allowed_tool_names: set[str] | None = None,
) -> list[dict]:
    return [
        policy.to_llm_spec()
        for policy in await list_tool_policies(
            include_approval_tools=include_approval_tools,
            allowed_tool_names=allowed_tool_names,
        )
    ]
