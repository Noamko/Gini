from uuid import UUID

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class Conversation(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "conversations"

    title: Mapped[str | None] = mapped_column(String(500))
    agent_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("agents.id"))
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)

    agent = relationship("Agent", lazy="selectin")
    messages = relationship("Message", back_populates="conversation", order_by="Message.created_at", lazy="selectin", cascade="all, delete-orphan", passive_deletes=True)
