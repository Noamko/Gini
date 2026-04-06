"""Integration tests for the backup/restore API."""


async def test_export_produces_valid_backup(client):
    """Export should return a well-formed backup JSON."""
    resp = await client.get("/api/backup/export")
    assert resp.status_code == 200
    data = resp.json()
    assert data["version"] == "1.2"
    assert data["includes_secrets"] is False
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


async def test_export_omits_credential_values_by_default(client):
    resp = await client.post("/api/credentials", json={
        "name": "backup-test-credential",
        "value": "super-secret",
    })
    assert resp.status_code == 201
    credential_id = resp.json()["id"]

    try:
        resp = await client.get("/api/backup/export")
        assert resp.status_code == 200
        credentials = resp.json()["credentials"]
        exported = next(c for c in credentials if c["name"] == "backup-test-credential")
        assert "encrypted_value" not in exported
        assert exported["has_secret"] is True

        resp = await client.get("/api/backup/export?include_secrets=true")
        assert resp.status_code == 200
        credentials = resp.json()["credentials"]
        exported = next(c for c in credentials if c["name"] == "backup-test-credential")
        assert exported["encrypted_value"]
    finally:
        await client.delete(f"/api/credentials/{credential_id}")


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
