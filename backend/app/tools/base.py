"""Base class for all Gini tools."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    success: bool = True
    output: str = ""
    error: str | None = None
    metadata: dict = field(default_factory=dict)


class BaseTool(ABC):
    """Abstract base class for tools."""

    name: str
    description: str
    parameters_schema: dict  # JSON Schema
    requires_sandbox: bool = False
    requires_approval: bool = False

    @abstractmethod
    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute the tool with the given parameters."""
        ...

    def to_llm_tool_spec(self) -> dict:
        """Convert to the format expected by LLM APIs for tool/function calling."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters_schema,
        }
