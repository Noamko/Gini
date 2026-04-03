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
    # Try built-in tool first
    tool = get_tool(tool_name)

    start = time.perf_counter()

    if tool:
        # Built-in tool
        try:
            if use_sandbox and tool.requires_sandbox:
                result = await _execute_in_sandbox(tool, arguments, allow_network=allow_network)
            else:
                result = await tool.execute(**arguments)
        except Exception as e:
            result = ToolResult(success=False, error=f"Tool execution error: {e}")
    else:
        # Try custom tool from DB
        result = await _execute_custom_tool(tool_name, arguments, use_sandbox, allow_network)

    duration_ms = round((time.perf_counter() - start) * 1000, 2)

    await logger.ainfo(
        "tool_executed",
        tool=tool_name,
        success=result.success,
        duration_ms=duration_ms,
        sandboxed=use_sandbox and (tool.requires_sandbox if tool else False),
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

    # Execute custom code in sandbox (safe) or directly
    if use_sandbox:
        return await _run_custom_in_sandbox(db_tool, arguments, allow_network)
    else:
        return await _run_custom_direct(db_tool, arguments)


async def _run_custom_direct(db_tool, arguments: dict) -> ToolResult:
    """Execute custom tool code directly in the backend process."""
    code = db_tool.code
    args_json = json.dumps(arguments)

    # Build a wrapper script that calls the user's function
    wrapper = f"""
import json, sys

# User-defined tool code
{code}

# Execute with arguments
args = json.loads('''{args_json}''')
try:
    result = execute(**args)
    if isinstance(result, dict):
        print(json.dumps(result))
    else:
        print(str(result))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
    sys.exit(1)
"""

    try:
        proc = await asyncio.create_subprocess_exec(
            "python3", "-c", wrapper,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
        output = stdout.decode("utf-8", errors="replace").strip()
        errors = stderr.decode("utf-8", errors="replace").strip()

        if proc.returncode != 0:
            return ToolResult(success=False, error=errors or output or f"Exit code: {proc.returncode}")

        # Try to parse as JSON error
        try:
            parsed = json.loads(output)
            if isinstance(parsed, dict) and "error" in parsed:
                return ToolResult(success=False, error=parsed["error"])
        except json.JSONDecodeError:
            pass

        return ToolResult(output=output[:50000])
    except asyncio.TimeoutError:
        return ToolResult(success=False, error="Custom tool timed out (60s)")
    except Exception as e:
        return ToolResult(success=False, error=str(e))


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
            command=command,
            timeout=timeout,
            allow_network=allow_network,
        )

        return ToolResult(
            success=sandbox_result.success,
            output=sandbox_result.output,
            error=f"Exit code: {sandbox_result.exit_code}" if not sandbox_result.success else None,
            metadata={"command": command, "exit_code": sandbox_result.exit_code, "sandboxed": True},
        )

    # For other sandboxed tools, fall back to direct execution
    return await tool.execute(**arguments)
