from typing import Any

import httpx

from app.tools.base import BaseTool, ToolResult


class WebFetchTool(BaseTool):
    name = "web_fetch"
    description = "Make an HTTP request to a URL. Supports GET, POST, PUT, and DELETE methods."
    parameters_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to fetch.",
            },
            "method": {
                "type": "string",
                "enum": ["GET", "POST", "PUT", "DELETE"],
                "description": "HTTP method. Defaults to GET.",
                "default": "GET",
            },
            "body": {
                "type": "string",
                "description": "Request body (JSON string). Used with POST/PUT.",
            },
            "headers": {
                "type": "object",
                "description": "Additional HTTP headers.",
                "additionalProperties": {"type": "string"},
            },
            "max_length": {
                "type": "integer",
                "description": "Maximum response length in characters. Defaults to 10000.",
                "default": 10000,
            },
        },
        "required": ["url"],
    }

    async def execute(
        self,
        url: str,
        method: str = "GET",
        body: str | None = None,
        headers: dict[str, str] | None = None,
        max_length: int = 10000,
        **kwargs: Any,
    ) -> ToolResult:
        try:
            req_headers = {"Content-Type": "application/json"} if body else {}
            if headers:
                req_headers.update(headers)

            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                response = await client.request(
                    method=method.upper(),
                    url=url,
                    headers=req_headers,
                    content=body,
                )
                response.raise_for_status()

                content = response.text
                if len(content) > max_length:
                    content = content[:max_length] + f"\n\n... truncated ({len(response.text)} total chars)"

                return ToolResult(
                    output=content,
                    metadata={
                        "url": url,
                        "method": method.upper(),
                        "status_code": response.status_code,
                        "content_type": response.headers.get("content-type", ""),
                        "length": len(response.text),
                    },
                )
        except httpx.HTTPStatusError as e:
            return ToolResult(success=False, error=f"HTTP {e.response.status_code}: {e.response.reason_phrase}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))
