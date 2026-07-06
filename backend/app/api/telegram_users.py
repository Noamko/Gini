"""Telegram user access-control CRUD."""

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.telegram_user import TelegramUser
from app.schemas.telegram_user import TelegramUserCreate, TelegramUserResponse, TelegramUserUpdate

logger = structlog.get_logger("telegram_users_api")

router = APIRouter(prefix="/api/telegram-users", tags=["telegram-users"])


@router.get("", response_model=list[TelegramUserResponse])
async def list_telegram_users(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(TelegramUser).order_by(
            # Pending access requests surface first so the admin sees them.
            case((TelegramUser.status == "pending", 0), else_=1),
            TelegramUser.created_at.desc(),
        )
    )
    return result.scalars().all()


@router.post("", response_model=TelegramUserResponse, status_code=201)
async def create_telegram_user(body: TelegramUserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TelegramUser).where(TelegramUser.telegram_id == body.telegram_id))
    if result.scalar_one_or_none():
        raise HTTPException(409, "Telegram ID already registered")

    user = TelegramUser(
        telegram_id=body.telegram_id,
        username=body.username,
        note=body.note,
        status=body.status,
        can_chat=body.can_chat,
        can_receive=body.can_receive,
        can_approve=body.can_approve,
        daily_budget_usd=body.daily_budget_usd,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    await logger.ainfo("telegram_user_created", telegram_id=str(user.telegram_id), status=user.status)
    return user


@router.put("/{user_id}", response_model=TelegramUserResponse)
async def update_telegram_user(user_id: UUID, body: TelegramUserUpdate, db: AsyncSession = Depends(get_db)):
    user = await db.get(TelegramUser, user_id)
    if not user:
        raise HTTPException(404, "Telegram user not found")

    # exclude_unset so an explicit null clears daily_budget_usd/note.
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(user, field, value)

    await db.commit()
    await db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=204)
async def delete_telegram_user(user_id: UUID, db: AsyncSession = Depends(get_db)):
    user = await db.get(TelegramUser, user_id)
    if not user:
        raise HTTPException(404, "Telegram user not found")
    await db.delete(user)
    await db.commit()
