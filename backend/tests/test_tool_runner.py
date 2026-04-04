"""Tests for tool execution logic."""
from unittest.mock import AsyncMock, patch

from app.services.tool_runner import execute_tool
from app.tools.base import ToolResult


async def test_execute_builtin_tool():
    """Built-in tools should execute and return a ToolResult."""
    # read_file with a nonexistent path should return an error gracefully
    result = await execute_tool("read_file", {"path": "/tmp/gini_test_nonexistent_file.txt"})
    assert isinstance(result, ToolResult)
    assert result.success is False
    assert "duration_ms" in result.metadata


async def test_execute_unknown_tool():
    """Unknown tool names that aren't built-in fall through to custom tool lookup."""
    # Verify the tool isn't in the built-in registry
    from app.tools.registry import get_tool
    assert get_tool("totally_fake_tool_xyz") is None

    # Mock _execute_custom_tool to avoid DB dependency
    mock_result = ToolResult(success=False, error="Unknown tool: totally_fake_tool_xyz")
    with patch("app.services.tool_runner._execute_custom_tool", AsyncMock(return_value=mock_result)):
        result = await execute_tool("totally_fake_tool_xyz", {"foo": "bar"})

    assert isinstance(result, ToolResult)
    assert result.success is False
    assert "Unknown tool" in result.error


async def test_execute_tool_tracks_duration():
    """All tool executions should have duration_ms in metadata."""
    result = await execute_tool("read_file", {"path": "/dev/null"})
    assert "duration_ms" in result.metadata
    assert isinstance(result.metadata["duration_ms"], float)
