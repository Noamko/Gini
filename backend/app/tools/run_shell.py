import asyncio
from typing import Any

from app.tools.base import BaseTool, ToolResult


class RunShellTool(BaseTool):
    name = "run_shell"
    description = "Execute a shell command and return stdout/stderr. Use with caution."
    requires_sandbox = True
    requires_approval = True
    parameters_schema = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute.",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds. Defaults to 30.",
                "default": 30,
            },
            "credential_names": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Optional credential handles to inject as environment variables. "
                    "The backend maps each handle to a GINI_CRED_* env var."
                ),
                "default": [],
            },
        },
        "required": ["command"],
    }

    async def execute(
        self,
        command: str,
        timeout: int = 30,
        credential_names: list[str] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)

            output_parts = []
            if stdout:
                output_parts.append(stdout.decode("utf-8", errors="replace"))
            if stderr:
                output_parts.append(f"STDERR:\n{stderr.decode('utf-8', errors='replace')}")

            output = "\n".join(output_parts) if output_parts else "(no output)"

            return ToolResult(
                success=proc.returncode == 0,
                output=output,
                error=f"Exit code: {proc.returncode}" if proc.returncode != 0 else None,
                metadata={"command": command, "exit_code": proc.returncode},
            )
        except TimeoutError:
            return ToolResult(success=False, error=f"Command timed out after {timeout}s")
        except Exception as e:
            return ToolResult(success=False, error=str(e))
