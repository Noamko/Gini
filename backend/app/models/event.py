"""Event model for event bus persistence and HITL audit trail."""
from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.models.base import Base, TimestampMixin, UUIDMixin
from sqlalchemy.orm import Mapped, mapped_column


class Event(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "events"

    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    correlation_id: Mapped[str | None] = mapped_column(String(100), index=True)
    conversation_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), index=True)
    source: Mapped[str | None] = mapped_column(String(100))
    payload: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(50), default="created", index=True)
    result: Mapped[dict | None] = mapped_column(JSONB)
