"""add direct agent tool/credential grants and tool credential slots

Merges the two existing heads (add-code-to-tools + add-runtime-state-to-agent-runs) and adds the
direct-grant schema: agent_tools (with credential slot bindings), agent_credentials,
and tools.credential_slots. Purely additive — existing skill bundles keep working.

Revision ID: d7e8f9a0b1c2
Revises: e1f2a3b4c5d6, f1a2b3c4d5e6
Create Date: 2026-05-30 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d7e8f9a0b1c2"
down_revision: str | Sequence[str] | None = ("e1f2a3b4c5d6", "f1a2b3c4d5e6")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_tools",
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tool_name", sa.String(length=255), nullable=False),
        sa.Column("slot_bindings", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("agent_id", "tool_name"),
    )
    op.create_table(
        "agent_credentials",
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("credential_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["credential_id"], ["credentials.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("agent_id", "credential_id"),
    )
    op.add_column(
        "tools",
        sa.Column("credential_slots", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("tools", "credential_slots")
    op.drop_table("agent_credentials")
    op.drop_table("agent_tools")
