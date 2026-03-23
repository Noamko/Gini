from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_db, get_redis

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    return {"status": "ok", "app": settings.app_name, "version": settings.app_version}


@router.get("/health/db")
async def health_db(db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(text("SELECT 1"))
        result.scalar()
        return {"status": "ok", "service": "postgresql"}
    except Exception as e:
        return {"status": "error", "service": "postgresql", "detail": str(e)}


@router.get("/health/redis")
async def health_redis(redis=Depends(get_redis)):
    try:
        pong = await redis.ping()
        return {"status": "ok" if pong else "error", "service": "redis"}
    except Exception as e:
        return {"status": "error", "service": "redis", "detail": str(e)}


@router.get("/health/all")
async def health_all(db: AsyncSession = Depends(get_db), redis=Depends(get_redis)):
    db_status = "ok"
    redis_status = "ok"

    try:
        result = await db.execute(text("SELECT 1"))
        result.scalar()
    except Exception:
        db_status = "error"

    try:
        if not await redis.ping():
            redis_status = "error"
    except Exception:
        redis_status = "error"

    overall = "ok" if db_status == "ok" and redis_status == "ok" else "degraded"

    return {
        "status": overall,
        "app": settings.app_name,
        "version": settings.app_version,
        "services": {
            "postgresql": db_status,
            "redis": redis_status,
        },
    }
