"""Tests for application startup helpers."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.main import _normalize_db_owned_tool
from app.models.tool import Tool


async def test_normalize_db_owned_tool_switches_execution_to_db_code(db_session):
    tool = Tool(
        name="db_owned_test_tool",
        description="Test tool",
        parameters_schema={"type": "object"},
        implementation="app.tools.some_tool.SomeTool",
        requires_sandbox=False,
        requires_approval=False,
        is_builtin=True,
        is_active=True,
        code="async def execute():\n    return 'ok'\n",
    )
    db_session.add(tool)
    await db_session.commit()

    logger = SimpleNamespace(ainfo=AsyncMock())

    await _normalize_db_owned_tool(logger, db_session, "db_owned_test_tool")
    await db_session.commit()
    await db_session.refresh(tool)

    assert tool.is_builtin is False
    assert tool.implementation == "custom"
    logger.ainfo.assert_awaited_once()
