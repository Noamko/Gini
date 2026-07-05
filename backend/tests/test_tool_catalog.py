"""Tests for centralized tool policy lookups."""
from sqlalchemy import delete

from app.models.tool import Tool
from app.services.tool_catalog import get_tool_policy, list_tool_policies


async def test_custom_tool_policy_respects_flags(db_session):
    tool = Tool(
        name="test_policy_tool",
        description="policy test",
        parameters_schema={"type": "object", "properties": {}},
        implementation="custom",
        code="def execute(): return 'ok'",
        requires_sandbox=True,
        requires_approval=True,
        is_builtin=False,
        is_active=True,
    )
    db_session.add(tool)
    await db_session.commit()

    try:
        policy = await get_tool_policy("test_policy_tool")
        assert policy is not None
        assert policy.requires_sandbox is True
        assert policy.requires_approval is True

        policies = await list_tool_policies(include_approval_tools=False)
        assert "test_policy_tool" not in {p.name for p in policies}
    finally:
        await db_session.execute(delete(Tool).where(Tool.name == "test_policy_tool"))
        await db_session.commit()


async def test_list_tool_policies_can_filter_to_allowed_names(db_session):
    allowed_tool = Tool(
        name="allowed_db_tool",
        description="allowed",
        parameters_schema={"type": "object", "properties": {}},
        implementation="custom",
        code="def execute(): return 'ok'",
        requires_sandbox=False,
        requires_approval=False,
        is_builtin=False,
        is_active=True,
    )
    blocked_tool = Tool(
        name="blocked_db_tool",
        description="blocked",
        parameters_schema={"type": "object", "properties": {}},
        implementation="custom",
        code="def execute(): return 'ok'",
        requires_sandbox=False,
        requires_approval=False,
        is_builtin=False,
        is_active=True,
    )
    db_session.add_all([allowed_tool, blocked_tool])
    await db_session.commit()

    try:
        policies = await list_tool_policies(
            include_approval_tools=True,
            allowed_tool_names={"allowed_db_tool"},
        )
        assert "allowed_db_tool" in {p.name for p in policies}
        assert "blocked_db_tool" not in {p.name for p in policies}
    finally:
        await db_session.execute(delete(Tool).where(Tool.name.in_(["allowed_db_tool", "blocked_db_tool"])))
        await db_session.commit()


async def test_optin_tools_hidden_from_default_catalog():
    """Opt-in (default_catalog=False) tools like create_agent are hidden unless granted."""
    policies = await list_tool_policies(include_approval_tools=True)
    names = {p.name for p in policies}
    assert "create_agent" not in names  # opt-in, not granted
    assert "read_file" in names  # default-catalog builtin is present


async def test_optin_tools_shown_when_granted():
    policies = await list_tool_policies(
        include_approval_tools=True,
        optin_tool_names={"create_agent", "list_agents"},
    )
    names = {p.name for p in policies}
    assert {"create_agent", "list_agents"}.issubset(names)
    assert "create_workflow" not in names  # opt-in but not granted
    assert "read_file" in names  # default catalog still present (allowed_tool_names is None)


async def test_optin_is_additive_to_restricted_default_allowlist():
    """Granting an opt-in tool must not strip the restricted default allowlist."""
    policies = await list_tool_policies(
        include_approval_tools=True,
        allowed_tool_names={"read_file"},
        optin_tool_names={"create_agent"},
    )
    names = {p.name for p in policies}
    assert "read_file" in names
    assert "create_agent" in names
    assert "write_file" not in names  # default tool outside the restrictive allowlist
