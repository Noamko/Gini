from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import root_router
from app.config import settings
from app.dependencies import engine, redis_client
from app.observability.logging import setup_logging
from app.observability.middleware import CorrelationIdMiddleware, RequestLoggingMiddleware, RateLimitMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger = structlog.get_logger("lifespan")
    await logger.ainfo("starting", app=settings.app_name, version=settings.app_version)

    # Verify DB connection
    async with engine.connect() as conn:
        await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
    await logger.ainfo("database_connected")

    # Verify Redis connection
    await redis_client.ping()
    await logger.ainfo("redis_connected")

    # Mark stale runs as failed (from previous crashes/restarts)
    try:
        from app.dependencies import async_session
        from app.models.agent_run import AgentRun
        from sqlalchemy import update
        async with async_session() as db:
            result = await db.execute(
                update(AgentRun)
                .where(AgentRun.status.in_(["pending", "running"]))
                .values(status="failed", error="Cancelled: backend restarted")
            )
            if result.rowcount:
                await logger.ainfo("stale_runs_cleaned", count=result.rowcount)
            await db.commit()
    except Exception as e:
        await logger.awarning("stale_runs_cleanup_skipped", error=str(e)[:100])

    # Sync built-in tools to DB
    try:
        from app.dependencies import async_session as _as
        from app.models.tool import Tool
        from app.tools.registry import BUILTIN_TOOLS
        from sqlalchemy import select as _sel
        async with _as() as db:
            for tool_impl in BUILTIN_TOOLS:
                result = await db.execute(_sel(Tool).where(Tool.name == tool_impl.name))
                existing = result.scalar_one_or_none()
                if not existing:
                    db.add(Tool(
                        name=tool_impl.name, description=tool_impl.description,
                        parameters_schema=tool_impl.parameters_schema,
                        implementation=f"app.tools.{tool_impl.name}.{type(tool_impl).__name__}",
                        requires_sandbox=tool_impl.requires_sandbox,
                        requires_approval=tool_impl.requires_approval,
                        is_builtin=True,
                    ))
            await db.commit()
        await logger.ainfo("tools_synced")
    except Exception as e:
        await logger.awarning("tools_sync_skipped", error=str(e)[:100])

    # Start Telegram bot
    from app.services.telegram_bot import telegram_bot
    await telegram_bot.start()

    # Start scheduler
    from app.services.scheduler import scheduler
    await scheduler.start()

    yield

    # Graceful shutdown
    await scheduler.stop()
    await telegram_bot.stop()
    await logger.ainfo("shutting_down")
    # Give in-flight requests a moment to complete
    import asyncio
    await asyncio.sleep(1)
    await redis_client.aclose()
    await engine.dispose()
    await logger.ainfo("shutdown_complete")


def create_app() -> FastAPI:
    setup_logging(debug=settings.debug)

    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        lifespan=lifespan,
    )

    # Middleware (order matters: outermost first)
    application.add_middleware(RequestLoggingMiddleware)
    application.add_middleware(RateLimitMiddleware, max_requests=120, window_seconds=60)
    application.add_middleware(CorrelationIdMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"https?://(localhost(:\d+)?|gini\.tail3d4a2\.ts\.net(:\d+)?)",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routes
    application.include_router(root_router)

    return application


app = create_app()
