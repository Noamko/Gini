"""Integration tests for Redis connectivity and caching tools."""
from app.dependencies import redis_client


async def test_redis_ping():
    assert await redis_client.ping() is True


async def test_redis_set_get_delete():
    """Basic Redis operations work end-to-end."""
    key = "gini:test:integration"
    await redis_client.set(key, "hello")
    val = await redis_client.get(key)
    assert val == "hello"
    await redis_client.delete(key)
    assert await redis_client.get(key) is None
