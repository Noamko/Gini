"""Integration tests for the skills CRUD API."""


async def test_skill_lifecycle(client):
    """Create, update, assign to agent, then clean up."""
    # Create a skill
    resp = await client.post("/api/skills", json={
        "name": "test-skill",
        "description": "A test skill",
        "instructions": "When asked to test, respond with 'tested!'",
    })
    assert resp.status_code == 201
    skill = resp.json()
    skill_id = skill["id"]
    assert skill["name"] == "test-skill"
    assert skill["is_active"] is True

    # Create an agent to assign the skill to
    resp = await client.post("/api/agents", json={
        "name": "test-skill-agent",
        "system_prompt": "Skill test agent",
    })
    assert resp.status_code == 201
    agent_id = resp.json()["id"]

    try:
        # List skills
        resp = await client.get("/api/skills")
        assert resp.status_code == 200
        names = [s["name"] for s in resp.json()]
        assert "test-skill" in names

        # Update skill
        resp = await client.put(f"/api/skills/{skill_id}", json={
            "instructions": "Updated instructions",
        })
        assert resp.status_code == 200
        assert resp.json()["instructions"] == "Updated instructions"

        # Assign skill to agent
        resp = await client.post(f"/api/skills/{skill_id}/assign/{agent_id}")
        assert resp.status_code == 200

        # Verify agent has the skill
        resp = await client.get(f"/api/agents/{agent_id}/skills")
        assert resp.status_code == 200
        assert any(s["name"] == "test-skill" for s in resp.json())

        # Unassign
        resp = await client.delete(f"/api/skills/{skill_id}/assign/{agent_id}")
        assert resp.status_code == 200

    finally:
        await client.delete(f"/api/skills/{skill_id}")
        await client.delete(f"/api/agents/{agent_id}")


async def test_get_nonexistent_skill(client):
    resp = await client.get("/api/skills/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
