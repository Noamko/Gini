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


@dataclass(frozen=True)
class CredentialSlot:
    """A named credential requirement a tool declares.

    An agent binds a specific credential to each slot; at runtime only the bound
    credentials are decrypted and injected, keyed by ``name`` (never a global dict).
    """

    name: str
    type: str = "api_key"
    required: bool = True
    description: str = ""
    # When True, the slot binds a *list* of credentials and resolves to a list of values
    # (e.g. a Telegram chat slot that broadcasts to several chats). Single slots bind one.
    multi: bool = False

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.type,
            "required": self.required,
            "description": self.description,
            "multi": self.multi,
        }


class BaseTool(ABC):
    """Abstract base class for tools."""

    name: str
    description: str
    parameters_schema: dict  # JSON Schema
    requires_sandbox: bool = False
    requires_approval: bool = False
    # When False, the tool is "opt-in": it is hidden from the default catalog and
    # only exposed to an agent that is explicitly granted it (directly or via a skill).
    default_catalog: bool = True
    # Credential slots this tool needs. An agent's tool grant binds a credential to
    # each slot; the runtime injects only the bound slots into ``credentials``.
    credential_slots: list[CredentialSlot] = []
    # When True, the tool has no fixed slots: every credential explicitly bound on its
    # grant is injected under its binding name (e.g. run_shell exposes them as env vars).
    open_credential_slots: bool = False

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
