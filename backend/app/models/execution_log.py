"""Execution log model for tracing agent steps."""
from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class ExecutionLog(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "execution_logs"

    trace_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    conversation_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), index=True)
    agent_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), index=True)
    agent_name: Mapped[str | None] = mapped_column(String(255))
    step_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    step_name: Mapped[str | None] = mapped_column(String(255))
    step_order: Mapped[int] = mapped_column(Integer, default=0)
    input_data: Mapped[dict | None] = mapped_column(JSONB)
    output_data: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[float] = mapped_column(Float, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0)
    model: Mapped[str | None] = mapped_column(String(100))
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
