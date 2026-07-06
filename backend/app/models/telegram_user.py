"""Model for Telegram access control (who may talk to / be reached by the bot)."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class TelegramUser(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "telegram_users"

    # Signed: group/channel ids are negative.
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(255))
    first_name: Mapped[str | None] = mapped_column(String(255))
    last_name: Mapped[str | None] = mapped_column(String(255))
    note: Mapped[str | None] = mapped_column(Text)
    # "pending" | "active" | "blocked" — permissions below only apply when "active".
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    can_chat: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_receive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    can_approve: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    daily_budget_usd: Mapped[float | None] = mapped_column(Float)  # null = unlimited
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
