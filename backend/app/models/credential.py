"""Credential model with encrypted storage."""
from sqlalchemy import Boolean, Column, ForeignKey, String, Table, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin

# Junction: skill <-> credential
skill_credentials = Table(
    "skill_credentials",
    Base.metadata,
    Column("skill_id", UUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True),
    Column("credential_id", UUID(as_uuid=True), ForeignKey("credentials.id", ondelete="CASCADE"), primary_key=True),
)


class Credential(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "credentials"

    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    credential_type: Mapped[str] = mapped_column(String(50), nullable=False, default="api_key")
    encrypted_value: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
