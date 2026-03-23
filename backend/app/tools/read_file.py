from pathlib import Path
from typing import Any

from app.tools.base import BaseTool, ToolResult


class ReadFileTool(BaseTool):
    name = "read_file"
    description = "Read the contents of a file at the given path."
    parameters_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "The absolute or relative file path to read.",
            },
            "max_lines": {
                "type": "integer",
                "description": "Maximum number of lines to read. Defaults to 500.",
                "default": 500,
            },
        },
        "required": ["path"],
    }

    async def execute(self, path: str, max_lines: int = 500, **kwargs: Any) -> ToolResult:
        try:
            p = Path(path)
            if not p.exists():
                return ToolResult(success=False, error=f"File not found: {path}")
            if not p.is_file():
                return ToolResult(success=False, error=f"Not a file: {path}")

            text = p.read_text(encoding="utf-8", errors="replace")
            lines = text.splitlines()

            if len(lines) > max_lines:
                output = "\n".join(lines[:max_lines])
                output += f"\n\n... truncated ({len(lines)} total lines, showing first {max_lines})"
            else:
                output = text

            return ToolResult(
                output=output,
                metadata={"path": path, "lines": min(len(lines), max_lines), "total_lines": len(lines)},
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
