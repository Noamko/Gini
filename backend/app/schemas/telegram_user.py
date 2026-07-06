import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_serializer, field_validator


class TelegramUserCreate(BaseModel):
    telegram_id: str | int
    username: str | None = None
    note: str | None = None
    # Admin adding an id is approving it, so default to active.
    status: Literal["pending", "active", "blocked"] = "active"
    can_chat: bool = True
    can_receive: bool = True
    can_approve: bool = False
    daily_budget_usd: float | None = Field(default=None, ge=0)

    @field_validator("telegram_id")
    @classmethod
    def validate_telegram_id(cls, v: str | int) -> int:
        # Accept str to survive JS clients that stringify ids beyond 2^53.
        s = str(v)
        if not re.fullmatch(r"-?\d+", s):
            raise ValueError("telegram_id must be an integer (group/channel ids may have a leading '-')")
        return int(s)


class TelegramUserUpdate(BaseModel):
    username: str | None = None
    note: str | None = None
    status: Literal["pending", "active", "blocked"] | None = None
    can_chat: bool | None = None
    can_receive: bool | None = None
    can_approve: bool | None = None
    daily_budget_usd: float | None = Field(default=None, ge=0)


class TelegramUserResponse(BaseModel):
    id: UUID
    telegram_id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    note: str | None
    status: str
    can_chat: bool
    can_receive: bool
    can_approve: bool
    daily_budget_usd: float | None
    last_seen_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_serializer("telegram_id")
    def serialize_telegram_id(self, value: int) -> str:
        # Serialized as string: Telegram ids can exceed JS Number.MAX_SAFE_INTEGER.
        return str(value)
