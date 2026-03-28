"""add_workflow_id_to_schedules

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-03-28 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = "d0e1f2a3b4c5"
down_revision: Union[str, None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("schedules", sa.Column("workflow_id", UUID(as_uuid=True), sa.ForeignKey("workflows.id", ondelete="CASCADE"), nullable=True))
    op.alter_column("schedules", "agent_id", nullable=True)


def downgrade() -> None:
    op.drop_column("schedules", "workflow_id")
    op.alter_column("schedules", "agent_id", nullable=False)
