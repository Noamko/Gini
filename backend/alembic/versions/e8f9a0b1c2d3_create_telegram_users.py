"""create telegram_users table

Access-control registry for the Telegram bot: who may chat, receive messages,
approve HITL actions, and an optional per-user daily LLM budget.

Revision ID: e8f9a0b1c2d3
Revises: d7e8f9a0b1c2
Create Date: 2026-07-06 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e8f9a0b1c2d3"
down_revision: str | Sequence[str] | None = "d7e8f9a0b1c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "telegram_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("first_name", sa.String(length=255), nullable=True),
        sa.Column("last_name", sa.String(length=255), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("can_chat", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("can_receive", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("can_approve", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("daily_budget_usd", sa.Float(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_telegram_users_telegram_id", "telegram_users", ["telegram_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_telegram_users_telegram_id", table_name="telegram_users")
    op.drop_table("telegram_users")
