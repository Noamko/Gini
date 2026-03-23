from pathlib import Path
from typing import Any

from app.tools.base import BaseTool, ToolResult


class WriteFileTool(BaseTool):
    name = "write_file"
    description = "Write content to a file at the given path. Creates parent directories if needed."
    requires_approval = True
    parameters_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "The file path to write to.",
            },
            "content": {
                "type": "string",
                "description": "The content to write to the file.",
            },
        },
        "required": ["path", "content"],
    }

    async def execute(self, path: str, content: str, **kwargs: Any) -> ToolResult:
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return ToolResult(
                output=f"Successfully wrote {len(content)} bytes to {path}",
                metadata={"path": path, "bytes": len(content)},
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
