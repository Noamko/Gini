from sqlalchemy import Boolean, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class Agent(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "agents"

    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    llm_provider: Mapped[str] = mapped_column(String(50), nullable=False, default="anthropic")
    llm_model: Mapped[str] = mapped_column(String(100), nullable=False, default="claude-sonnet-4-20250514")
    temperature: Mapped[float] = mapped_column(Float, default=0.7)
    max_tokens: Mapped[int] = mapped_column(Integer, default=4096)
    state: Mapped[str] = mapped_column(String(50), nullable=False, default="idle", index=True)
    is_main: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_approve: Mapped[bool] = mapped_column(Boolean, default=False)
    daily_budget_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
