"""create_execution_logs_table

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-21 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'execution_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('trace_id', sa.String(100), nullable=False),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('agent_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('agent_name', sa.String(255), nullable=True),
        sa.Column('step_type', sa.String(50), nullable=False),
        sa.Column('step_name', sa.String(255), nullable=True),
        sa.Column('step_order', sa.Integer(), server_default='0'),
        sa.Column('input_data', postgresql.JSONB(), nullable=True),
        sa.Column('output_data', postgresql.JSONB(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('duration_ms', sa.Float(), server_default='0'),
        sa.Column('input_tokens', sa.Integer(), server_default='0'),
        sa.Column('output_tokens', sa.Integer(), server_default='0'),
        sa.Column('cost_usd', sa.Float(), server_default='0'),
        sa.Column('model', sa.String(100), nullable=True),
        sa.Column('metadata', postgresql.JSONB(), server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_execution_logs_trace_id', 'execution_logs', ['trace_id'])
    op.create_index('ix_execution_logs_conversation_id', 'execution_logs', ['conversation_id'])
    op.create_index('ix_execution_logs_agent_id', 'execution_logs', ['agent_id'])
    op.create_index('ix_execution_logs_step_type', 'execution_logs', ['step_type'])
    op.create_index('ix_execution_logs_created_at', 'execution_logs', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_execution_logs_created_at', table_name='execution_logs')
    op.drop_index('ix_execution_logs_step_type', table_name='execution_logs')
    op.drop_index('ix_execution_logs_agent_id', table_name='execution_logs')
    op.drop_index('ix_execution_logs_conversation_id', table_name='execution_logs')
    op.drop_index('ix_execution_logs_trace_id', table_name='execution_logs')
    op.drop_table('execution_logs')
