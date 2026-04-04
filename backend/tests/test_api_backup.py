"""Integration tests for the backup/restore API."""


async def test_export_produces_valid_backup(client):
    """Export should return a well-formed backup JSON."""
    resp = await client.get("/api/backup/export")
    assert resp.status_code == 200
    data = resp.json()
    assert data["version"] == "1.1"
    assert "exported_at" in data
    assert "agents" in data
    assert "tools" in data
    assert "skills" in data
    assert "credentials" in data
    # History tables
    assert "conversations" in data
    assert "messages" in data
    assert "agent_runs" in data
    assert "execution_logs" in data
    assert "events" in data
    assert isinstance(data["agents"], list)


async def test_export_roundtrip(client):
    """Create an agent, export, verify it's in the backup, then clean up."""
    # Create test data
    resp = await client.post("/api/agents", json={
        "name": "backup-test-agent",
        "system_prompt": "For backup testing",
    })
    assert resp.status_code == 201
    agent_id = resp.json()["id"]

    try:
        # Export
        resp = await client.get("/api/backup/export")
        assert resp.status_code == 200
        backup = resp.json()

        agent_names = [a["name"] for a in backup["agents"]]
        assert "backup-test-agent" in agent_names

    finally:
        await client.delete(f"/api/agents/{agent_id}")
