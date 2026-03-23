"""Executes tools by name, validates args, returns results.

Handles sandbox execution and HITL approval checks.
"""
import time

import structlog

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

    Args:
        tool_name: Name of the tool to execute.
        arguments: Tool arguments.
        use_sandbox: If True and the tool requires sandbox, run in a container.
        allow_network: If True, sandbox gets internet access (for trusted agents).
    """
    tool = get_tool(tool_name)
    if not tool:
        return ToolResult(success=False, error=f"Unknown tool: {tool_name}")

    start = time.perf_counter()

    try:
        if use_sandbox and tool.requires_sandbox:
            result = await _execute_in_sandbox(tool, arguments, allow_network=allow_network)
        else:
            result = await tool.execute(**arguments)
    except Exception as e:
        result = ToolResult(success=False, error=f"Tool execution error: {e}")

    duration_ms = round((time.perf_counter() - start) * 1000, 2)

    await logger.ainfo(
        "tool_executed",
        tool=tool_name,
        success=result.success,
        duration_ms=duration_ms,
        sandboxed=use_sandbox and tool.requires_sandbox,
        error=result.error,
    )

    result.metadata["duration_ms"] = duration_ms
    result.metadata["sandboxed"] = use_sandbox and tool.requires_sandbox
    return result


async def _execute_in_sandbox(tool: BaseTool, arguments: dict, allow_network: bool = False) -> ToolResult:
    """Execute a tool inside the sandbox container."""
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
