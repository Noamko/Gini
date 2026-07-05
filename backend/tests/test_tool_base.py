"""Tests for tool base classes and registry."""
from app.tools.base import BaseTool, ToolResult
from app.tools.registry import get_all_tools, get_llm_tool_specs, get_tool


def test_tool_result_defaults():
    r = ToolResult()
    assert r.success is True
    assert r.output == ""
    assert r.error is None
    assert r.metadata == {}


def test_tool_result_error():
    r = ToolResult(success=False, error="something broke")
    assert r.success is False
    assert r.error == "something broke"


def test_tool_result_metadata_not_shared():
    """Each ToolResult should get its own metadata dict."""
    a = ToolResult()
    b = ToolResult()
    a.metadata["key"] = "value"
    assert "key" not in b.metadata


def test_builtin_tools_registered():
    """All built-in tools should be registered and retrievable."""
    tools = get_all_tools()
    assert len(tools) >= 3  # at least read_file, write_file, run_shell

    for tool in tools:
        assert isinstance(tool, BaseTool)
        assert get_tool(tool.name) is tool


def test_unknown_tool_returns_none():
    assert get_tool("nonexistent_tool_xyz") is None


def test_default_catalog_default_true():
    """Ordinary tools are in the default catalog."""
    assert BaseTool.default_catalog is True
    assert get_tool("read_file").default_catalog is True


def test_meta_tools_are_optin():
    """Agent-management tools are registered but opt-in (hidden from the default catalog)."""
    for name in ("create_agent", "list_agents", "create_workflow", "create_webhook", "create_tool"):
        tool = get_tool(name)
        assert tool is not None, f"{name} should be registered"
        assert tool.default_catalog is False, f"{name} should be opt-in"
    # Create operations require approval; the discovery helper does not.
    assert get_tool("create_agent").requires_approval is True
    assert get_tool("list_agents").requires_approval is False


def test_llm_tool_specs_format():
    """Tool specs should have the required fields for LLM APIs."""
    specs = get_llm_tool_specs()
    assert len(specs) > 0

    for spec in specs:
        assert "name" in spec
        assert "description" in spec
        assert "input_schema" in spec
        assert isinstance(spec["input_schema"], dict)


def test_tool_to_llm_spec():
    """BaseTool.to_llm_tool_spec() should return well-formed spec."""
    tool = get_all_tools()[0]
    spec = tool.to_llm_tool_spec()
    assert spec["name"] == tool.name
    assert spec["description"] == tool.description
    assert spec["input_schema"] == tool.parameters_schema
