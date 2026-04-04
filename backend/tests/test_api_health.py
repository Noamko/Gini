"""Integration tests for the health endpoints."""


async def test_health_basic(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["app"] == "Gini"


async def test_health_db(client):
    resp = await client.get("/health/db")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "postgresql"


async def test_health_redis(client):
    resp = await client.get("/health/redis")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "redis"


async def test_health_all(client):
    resp = await client.get("/health/all")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["services"]["postgresql"] == "ok"
    assert data["services"]["redis"] == "ok"
