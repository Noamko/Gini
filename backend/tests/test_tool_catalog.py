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
