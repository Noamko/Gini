"""Tool registry — core built-in tools only. Other tools live in the DB as custom tools."""
from app.tools.base import BaseTool
from app.tools.delegate_task import DelegateTaskTool
from app.tools.read_file import ReadFileTool
from app.tools.run_shell import RunShellTool
from app.tools.web_fetch import WebFetchTool
from app.tools.write_file import WriteFileTool

# Core built-in tools (not editable from UI)
BUILTIN_TOOLS: list[BaseTool] = [
    ReadFileTool(),
    WriteFileTool(),
    RunShellTool(),
    WebFetchTool(),
    DelegateTaskTool(),
]

_tools_by_name: dict[str, BaseTool] = {t.name: t for t in BUILTIN_TOOLS}


def get_tool(name: str) -> BaseTool | None:
    return _tools_by_name.get(name)


def get_all_tools() -> list[BaseTool]:
    return BUILTIN_TOOLS


def get_llm_tool_specs() -> list[dict]:
    """Get tool specs formatted for LLM API calls (built-in only, sync)."""
    return [t.to_llm_tool_spec() for t in BUILTIN_TOOLS]


async def get_all_tool_specs() -> list[dict]:
    """Get tool specs for ALL tools (built-in + active custom from DB)."""
    specs = get_llm_tool_specs()

    from sqlalchemy import select

    from app.dependencies import async_session
    from app.models.tool import Tool
    async with async_session() as db:
        result = await db.execute(
            select(Tool).where(Tool.is_active == True).where(Tool.is_builtin == False).where(Tool.code.isnot(None))
        )
        for t in result.scalars().all():
            specs.append({
                "name": t.name,
                "description": t.description,
                "input_schema": t.parameters_schema,
            })

    return specs
