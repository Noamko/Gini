from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import root_router
from app.config import settings
from app.dependencies import engine, redis_client
from app.observability.logging import setup_logging
from app.observability.middleware import CorrelationIdMiddleware, RateLimitMiddleware, RequestLoggingMiddleware


async def _normalize_db_owned_tool(logger, db, tool_name: str) -> None:
    """Ensure a DB-owned tool executes its stored code rather than an import path."""
    from sqlalchemy import select

    from app.models.tool import Tool

    result = await db.execute(select(Tool).where(Tool.name == tool_name))
    tool = result.scalar_one_or_none()
    if not tool:
        return

    if tool.is_builtin:
        tool.is_builtin = False

    if tool.implementation != "custom" and tool.code:
        tool.implementation = "custom"
        await logger.ainfo("tool_normalized_to_db_owned", tool=tool_name)


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
        from sqlalchemy import update

        from app.dependencies import async_session
        from app.models.agent_run import AgentRun
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

    # Sync tools to DB (built-in + custom defaults)
    try:
        import inspect

        from sqlalchemy import select as _sel

        from app.dependencies import async_session as _as
        from app.models.tool import Tool
        from app.tools.cache import CacheDeleteTool, CacheGetTool, CacheListTool, CacheSetTool
        from app.tools.registry import BUILTIN_TOOLS

        # Tools that should be custom (editable) with their source code
        from app.tools.send_telegram import SendTelegramMediaGroupTool, SendTelegramPhotoTool, SendTelegramTool

        custom_tool_classes = [
            SendTelegramTool(), SendTelegramPhotoTool(), SendTelegramMediaGroupTool(),
            CacheSetTool(), CacheGetTool(), CacheDeleteTool(), CacheListTool(),
        ]

        async with _as() as db:
            # Sync core built-in tools
            for tool_impl in BUILTIN_TOOLS:
                result = await db.execute(_sel(Tool).where(Tool.name == tool_impl.name))
                existing = result.scalar_one_or_none()
                if not existing:
                    db.add(Tool(
                        name=tool_impl.name, description=tool_impl.description,
                        parameters_schema=tool_impl.parameters_schema,
                        implementation=f"{type(tool_impl).__module__}.{type(tool_impl).__name__}",
                        requires_sandbox=tool_impl.requires_sandbox,
                        requires_approval=tool_impl.requires_approval,
                        is_builtin=True,
                    ))

            # Sync custom tools (editable from UI)
            for tool_impl in custom_tool_classes:
                module = type(tool_impl).__module__
                class_name = type(tool_impl).__name__
                impl_path = f"{module}.{class_name}"

                result = await db.execute(_sel(Tool).where(Tool.name == tool_impl.name))
                existing = result.scalar_one_or_none()
                if existing:
                    # Mark as not built-in if it was previously
                    if existing.is_builtin:
                        existing.is_builtin = False
                    # Fix implementation path if wrong
                    if existing.implementation != impl_path:
                        existing.implementation = impl_path
                    # Set code if not already set
                    if not existing.code:
                        try:
                            existing.code = inspect.getsource(inspect.getmodule(type(tool_impl)))
                        except Exception as e:
                            await logger.adebug("tool_source_unavailable", tool=tool_impl.name, error=str(e))
                else:
                    try:
                        source = inspect.getsource(inspect.getmodule(type(tool_impl)))
                    except Exception:
                        source = None
                    db.add(Tool(
                        name=tool_impl.name, description=tool_impl.description,
                        parameters_schema=tool_impl.parameters_schema,
                        implementation=impl_path,
                        requires_sandbox=tool_impl.requires_sandbox,
                        requires_approval=tool_impl.requires_approval,
                        is_builtin=False,
                        code=source,
                    ))

            await _normalize_db_owned_tool(logger, db, "yad2_search")
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
