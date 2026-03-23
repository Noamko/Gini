"""Model for multi-agent workflow chains."""
from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class Workflow(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "workflows"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # Steps stored as JSON array:
    # [{"agent_id": "...", "agent_name": "...", "instructions": "...", "pass_output": true}]
    steps: Mapped[list] = mapped_column(JSONB, default=list)
