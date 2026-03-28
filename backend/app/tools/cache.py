"""Agent cache tools — namespaced Redis key-value storage per agent."""
from typing import Any

from app.dependencies import redis_client
from app.tools.base import BaseTool, ToolResult

CACHE_PREFIX = "gini:agent_cache:"
DEFAULT_TTL = 86400  # 24 hours


class CacheSetTool(BaseTool):
    name = "cache_set"
    description = "Store a value in the agent's local cache. Data persists across runs (24h default TTL). Use for scraped results, session state, or intermediate data."
    parameters_schema = {
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "Cache key name.",
            },
            "value": {
                "type": "string",
                "description": "Value to store (string). For JSON data, stringify it first.",
            },
            "ttl": {
                "type": "integer",
                "description": "Time-to-live in seconds. Default 86400 (24 hours). Set 0 for no expiry.",
            },
        },
        "required": ["key", "value"],
    }

    async def execute(self, key: str, value: str, ttl: int = DEFAULT_TTL, **kwargs: Any) -> ToolResult:
        try:
            full_key = f"{CACHE_PREFIX}{key}"
            if ttl > 0:
                await redis_client.setex(full_key, ttl, value)
            else:
                await redis_client.set(full_key, value)
            return ToolResult(output=f"Cached '{key}' ({len(value)} chars, ttl={ttl}s)")
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class CacheGetTool(BaseTool):
    name = "cache_get"
    description = "Retrieve a value from the agent's local cache. Returns the stored string or empty if not found."
    parameters_schema = {
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "Cache key name to retrieve.",
            },
        },
        "required": ["key"],
    }

    async def execute(self, key: str, **kwargs: Any) -> ToolResult:
        try:
            full_key = f"{CACHE_PREFIX}{key}"
            value = await redis_client.get(full_key)
            if value is None:
                return ToolResult(output="(not found)")
            return ToolResult(output=value, metadata={"key": key, "length": len(value)})
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class CacheDeleteTool(BaseTool):
    name = "cache_delete"
    description = "Delete a key from the agent's local cache."
    parameters_schema = {
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "Cache key name to delete.",
            },
        },
        "required": ["key"],
    }

    async def execute(self, key: str, **kwargs: Any) -> ToolResult:
        try:
            full_key = f"{CACHE_PREFIX}{key}"
            deleted = await redis_client.delete(full_key)
            return ToolResult(output=f"Deleted '{key}'" if deleted else f"Key '{key}' not found")
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class CacheListTool(BaseTool):
    name = "cache_list"
    description = "List all keys in the agent cache."
    parameters_schema = {
        "type": "object",
        "properties": {},
    }

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            keys = []
            async for key in redis_client.scan_iter(f"{CACHE_PREFIX}*"):
                short_key = key.removeprefix(CACHE_PREFIX) if isinstance(key, str) else key.decode().removeprefix(CACHE_PREFIX)
                keys.append(short_key)
            if not keys:
                return ToolResult(output="Cache is empty")
            return ToolResult(output="\n".join(sorted(keys)), metadata={"count": len(keys)})
        except Exception as e:
            return ToolResult(success=False, error=str(e))
