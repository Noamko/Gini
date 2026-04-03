"""Executes tools by name, validates args, returns results.

Handles built-in tools, custom Python tools, and sandbox execution.
"""
import asyncio
import json
import time

import structlog
from sqlalchemy import select

from app.tools.base import BaseTool, ToolResult
from app.tools.registry import get_tool
from app.sandbox.manager import sandbox_manager

logger = structlog.get_logger("tool_runner")


async def execute_tool(
    tool_name: str,
    arguments: dict,
    use_sandbox: bool = False,
    allow_network: bool = False,
) -> ToolResult:
    """Look up and execute a tool by name.

    Checks built-in registry first, then falls back to custom tools from DB.
    """
    tool = get_tool(tool_name)

    start = time.perf_counter()

    if tool:
        try:
            if use_sandbox and tool.requires_sandbox:
                result = await _execute_in_sandbox(tool, arguments, allow_network=allow_network)
            else:
                result = await tool.execute(**arguments)
        except Exception as e:
            result = ToolResult(success=False, error=f"Tool execution error: {e}")
    else:
        result = await _execute_custom_tool(tool_name, arguments, use_sandbox, allow_network)

    duration_ms = round((time.perf_counter() - start) * 1000, 2)

    await logger.ainfo(
        "tool_executed",
        tool=tool_name,
        success=result.success,
        duration_ms=duration_ms,
        error=result.error,
    )

    result.metadata["duration_ms"] = duration_ms
    return result


async def _execute_custom_tool(
    tool_name: str, arguments: dict, use_sandbox: bool, allow_network: bool,
) -> ToolResult:
    """Execute a custom tool by running its Python code from the DB."""
    from app.dependencies import async_session
    from app.models.tool import Tool

    async with async_session() as db:
        result = await db.execute(
            select(Tool).where(Tool.name == tool_name).where(Tool.is_active == True)
        )
        db_tool = result.scalar_one_or_none()

    if not db_tool:
        return ToolResult(success=False, error=f"Unknown tool: {tool_name}")

    if not db_tool.code:
        return ToolResult(success=False, error=f"Tool '{tool_name}' has no code defined")

    if use_sandbox and db_tool.requires_sandbox:
        return await _run_custom_in_sandbox(db_tool, arguments, allow_network)
    else:
        return await _run_custom_inprocess(db_tool, arguments)


async def _run_custom_inprocess(db_tool, arguments: dict) -> ToolResult:
    """Execute custom tool code in-process with access to app context."""

    # First try: import the tool class from its implementation path
    if db_tool.implementation and db_tool.implementation != "custom":
        try:
            parts = db_tool.implementation.rsplit(".", 1)
            if len(parts) == 2:
                module_path, class_name = parts
                import importlib
                module = importlib.import_module(module_path)
                tool_class = getattr(module, class_name)
                tool_instance = tool_class()
                result = await tool_instance.execute(**arguments)
                return result
        except Exception:
            pass  # Fall through to code execution

    # Second try: execute the code field
    code = db_tool.code
    if not code:
        return ToolResult(success=False, error=f"Tool '{db_tool.name}' has no code and implementation '{db_tool.implementation}' could not be loaded")

    namespace = {
        "__builtins__": __builtins__,
        "asyncio": asyncio,
        "json": json,
    }

    try:
        exec(code, namespace)

        execute_fn = namespace.get("execute")
        if not execute_fn:
            return ToolResult(success=False, error="Tool code must define an execute() function")

        if asyncio.iscoroutinefunction(execute_fn):
            result = await execute_fn(**arguments)
        else:
            result = await asyncio.to_thread(execute_fn, **arguments)

        if isinstance(result, ToolResult):
            return result
        elif isinstance(result, dict):
            if "error" in result and not result.get("output"):
                return ToolResult(success=False, error=str(result["error"]))
            return ToolResult(output=json.dumps(result, ensure_ascii=False, default=str))
        else:
            return ToolResult(output=str(result)[:50000])

    except Exception as e:
        return ToolResult(success=False, error=f"Custom tool error: {e}")


async def _run_custom_in_sandbox(db_tool, arguments: dict, allow_network: bool) -> ToolResult:
    """Execute custom tool code in a sandbox container."""
    code = db_tool.code
    args_json = json.dumps(arguments).replace("'", "'\\''")

    wrapper = f"""python3 -c "
import json, sys

{code}

args = json.loads('{args_json}')
try:
    result = execute(**args)
    if isinstance(result, dict):
        print(json.dumps(result))
    else:
        print(str(result))
except Exception as e:
    print(json.dumps({{'error': str(e)}}))
    sys.exit(1)
"
"""
    sandbox_result = await sandbox_manager.execute(
        command=wrapper, timeout=60, allow_network=allow_network,
    )

    if not sandbox_result.success:
        return ToolResult(success=False, error=sandbox_result.output or f"Exit code: {sandbox_result.exit_code}")

    output = sandbox_result.output.strip()
    try:
        parsed = json.loads(output)
        if isinstance(parsed, dict) and "error" in parsed:
            return ToolResult(success=False, error=parsed["error"])
    except json.JSONDecodeError:
        pass

    return ToolResult(output=output[:50000])


async def _execute_in_sandbox(tool: BaseTool, arguments: dict, allow_network: bool = False) -> ToolResult:
    """Execute a built-in tool inside the sandbox container."""
    if tool.name == "run_shell":
        command = arguments.get("command", "")
        timeout = arguments.get("timeout", 30)

        sandbox_result = await sandbox_manager.execute(
            command=command, timeout=timeout, allow_network=allow_network,
        )

        return ToolResult(
            success=sandbox_result.success,
            output=sandbox_result.output,
            error=f"Exit code: {sandbox_result.exit_code}" if not sandbox_result.success else None,
            metadata={"command": command, "exit_code": sandbox_result.exit_code, "sandboxed": True},
        )

    return await tool.execute(**arguments)
