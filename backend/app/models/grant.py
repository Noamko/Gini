"""Direct agent grants: tools (with credential-slot bindings) and credentials.

These let an agent hold tools and credentials directly, without funneling them
through a skill. Skills remain optional reusable bundles; an agent's effective
tools/credentials are the union of its direct grants and its assigned skills.
"""

from sqlalchemy import Column, ForeignKey, String, Table
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.models.base import Base

# Direct grant: agent -> tool. ``slot_bindings`` maps each declared credential slot
# name to a credential id ({slot_name: credential_id}); resolved against the agent's
# credential pool at execution time.
agent_tools = Table(
    "agent_tools",
    Base.metadata,
    Column("agent_id", UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True),
    Column("tool_name", String(255), primary_key=True),
    Column("slot_bindings", JSONB, nullable=False, server_default="{}"),
)

# Direct grant: agent -> credential.
agent_credentials = Table(
    "agent_credentials",
    Base.metadata,
    Column("agent_id", UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True),
    Column("credential_id", UUID(as_uuid=True), ForeignKey("credentials.id", ondelete="CASCADE"), primary_key=True),
)
