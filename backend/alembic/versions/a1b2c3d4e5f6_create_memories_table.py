"""create_memories_table

Revision ID: a1b2c3d4e5f6
Revises: 5e72c289289b
Create Date: 2026-03-21 21:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '5e72c289289b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        'memories',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('agent_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('source', sa.String(100), nullable=False, server_default='conversation'),
        sa.Column('source_id', sa.String(255), nullable=True),
        sa.Column('embedding', Vector(1536), nullable=False),
        sa.Column('metadata', postgresql.JSONB(), server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_memories_agent_id', 'memories', ['agent_id'])
    op.create_index(
        'ix_memories_embedding',
        'memories',
        ['embedding'],
        postgresql_using='ivfflat',
        postgresql_with={'lists': 100},
        postgresql_ops={'embedding': 'vector_cosine_ops'},
    )

    # Add use_memory column to agents
    op.add_column('agents', sa.Column('use_memory', sa.Boolean(), server_default='false', nullable=False))


def downgrade() -> None:
    op.drop_column('agents', 'use_memory')
    op.drop_index('ix_memories_embedding', table_name='memories')
    op.drop_index('ix_memories_agent_id', table_name='memories')
    op.drop_table('memories')
    op.execute("DROP EXTENSION IF EXISTS vector")
