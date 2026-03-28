"""Tool registry — discovers and provides access to all built-in tools."""
from app.tools.base import BaseTool
from app.tools.read_file import ReadFileTool
from app.tools.write_file import WriteFileTool
from app.tools.run_shell import RunShellTool
from app.tools.web_fetch import WebFetchTool
from app.tools.delegate_task import DelegateTaskTool
from app.tools.send_telegram import SendTelegramTool, SendTelegramPhotoTool, SendTelegramMediaGroupTool

# All built-in tools
BUILTIN_TOOLS: list[BaseTool] = [
    ReadFileTool(),
    WriteFileTool(),
    RunShellTool(),
    WebFetchTool(),
    DelegateTaskTool(),
    SendTelegramTool(),
    SendTelegramPhotoTool(),
    SendTelegramMediaGroupTool(),
]

_tools_by_name: dict[str, BaseTool] = {t.name: t for t in BUILTIN_TOOLS}


def get_tool(name: str) -> BaseTool | None:
    return _tools_by_name.get(name)


def get_all_tools() -> list[BaseTool]:
    return BUILTIN_TOOLS


def get_llm_tool_specs() -> list[dict]:
    """Get tool specs formatted for LLM API calls."""
    return [t.to_llm_tool_spec() for t in BUILTIN_TOOLS if not t.requires_sandbox or True]
