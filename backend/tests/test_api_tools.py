"""Integration tests for the tools CRUD API."""


async def test_create_custom_tool(client):
    """Create a custom tool, verify it, then delete it."""
    resp = await client.post("/api/tools", json={
        "name": "test_greet",
        "description": "A test greeting tool",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name to greet"},
            },
            "required": ["name"],
        },
        "code": "async def execute(name: str) -> str:\n    return f'Hello, {name}!'",
    })
    assert resp.status_code == 201
    tool = resp.json()
    tool_id = tool["id"]
    assert tool["name"] == "test_greet"
    assert tool["is_builtin"] is False
    assert tool["is_active"] is True

    try:
        # Get by ID
        resp = await client.get(f"/api/tools/{tool_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "test_greet"

        # Get source
        resp = await client.get(f"/api/tools/{tool_id}/source")
        assert resp.status_code == 200
        assert "execute" in resp.json()["source"]

        # Update
        resp = await client.put(f"/api/tools/{tool_id}", json={
            "description": "Updated greeting tool",
        })
        assert resp.status_code == 200
        assert resp.json()["description"] == "Updated greeting tool"

        # List — should include our tool
        resp = await client.get("/api/tools")
        assert resp.status_code == 200
        names = [t["name"] for t in resp.json()["items"]]
        assert "test_greet" in names

    finally:
        resp = await client.delete(f"/api/tools/{tool_id}")
        assert resp.status_code == 204


async def test_delete_nonexistent_tool(client):
    resp = await client.delete("/api/tools/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
