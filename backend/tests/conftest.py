"""Shared test fixtures for both unit and integration tests."""
import os

import pytest
from httpx import ASGITransport, AsyncClient

# Point at the local Docker DB and Redis before any app code is imported
os.environ["DATABASE_URL"] = "postgresql+asyncpg://gini:gini_dev_password@localhost:5432/gini"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"


@pytest.fixture
def tool_result_factory():
    """Factory for creating ToolResult instances."""
    from app.tools.base import ToolResult

    def _make(**kwargs):
        return ToolResult(**kwargs)

    return _make


# ---------------------------------------------------------------------------
# Integration fixtures
# ---------------------------------------------------------------------------

# Single event loop for the entire test session — required because the
# module-level engine/redis_client singletons bind to the first loop.
@pytest.fixture(scope="session")
def event_loop_policy():
    import asyncio
    return asyncio.DefaultEventLoopPolicy()


_test_app = None


def get_test_app():
    """Create a single FastAPI app instance (no lifespan — skips Telegram/scheduler)."""
    global _test_app
    if _test_app is None:
        from fastapi import FastAPI

        from app.api.router import root_router

        app = FastAPI()
        app.include_router(root_router)
        _test_app = app
    return _test_app


@pytest.fixture
async def client():
    """Async HTTP client that talks to the test app in-process."""
    app = get_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def db_session():
    """Raw async DB session for direct data setup/teardown."""
    from app.dependencies import async_session

    async with async_session() as session:
        yield session
