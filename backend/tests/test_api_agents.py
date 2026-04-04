"""Integration tests for the agents CRUD API."""
from httpx import ASGITransport, AsyncClient


async def test_create_and_get_agent(client):
    """Full lifecycle: create -> get -> list -> update -> delete."""
    # Create
    resp = await client.post("/api/agents", json={
        "name": "test-agent-crud",
        "system_prompt": "You are a test agent.",
        "description": "Created by integration test",
    })
    assert resp.status_code == 201
    agent = resp.json()
    agent_id = agent["id"]
    assert agent["name"] == "test-agent-crud"
    assert agent["llm_provider"] == "anthropic"
    assert agent["state"] == "idle"
    assert agent["is_active"] is True

    try:
        # Get by ID
        resp = await client.get(f"/api/agents/{agent_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "test-agent-crud"

        # List — should include our agent
        resp = await client.get("/api/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        names = [a["name"] for a in data["items"]]
        assert "test-agent-crud" in names

        # Update
        resp = await client.put(f"/api/agents/{agent_id}", json={
            "description": "Updated description",
            "temperature": 0.3,
        })
        assert resp.status_code == 200
        assert resp.json()["description"] == "Updated description"
        assert resp.json()["temperature"] == 0.3

    finally:
        # Cleanup
        resp = await client.delete(f"/api/agents/{agent_id}")
        assert resp.status_code == 204


async def test_get_nonexistent_agent(client):
    resp = await client.get("/api/agents/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


async def test_create_duplicate_agent_name(client):
    """Duplicate agent names should fail with a DB constraint error."""
    from tests.conftest import get_test_app

    payload = {"name": "test-agent-dup", "system_prompt": "dup test"}
    resp1 = await client.post("/api/agents", json=payload)
    assert resp1.status_code == 201
    agent_id = resp1.json()["id"]

    try:
        # Use a client that doesn't raise app exceptions so we get the 500 response
        transport = ASGITransport(app=get_test_app(), raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp2 = await c.post("/api/agents", json=payload)
        assert resp2.status_code == 500  # unique constraint violation
    finally:
        await client.delete(f"/api/agents/{agent_id}")
