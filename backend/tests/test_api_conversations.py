"""Integration tests for the conversations API."""


async def test_conversation_lifecycle(client):
    """Create a conversation, list it, then delete it."""
    # Create
    resp = await client.post("/api/conversations", json={
        "title": "Test Conversation",
    })
    assert resp.status_code == 201
    conv = resp.json()
    conv_id = conv["id"]
    assert conv["title"] == "Test Conversation"

    try:
        # Get by ID
        resp = await client.get(f"/api/conversations/{conv_id}")
        assert resp.status_code == 200
        assert resp.json()["title"] == "Test Conversation"

        # List
        resp = await client.get("/api/conversations")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

        # Messages (should be empty for new conversation)
        resp = await client.get(f"/api/conversations/{conv_id}/messages")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0
        assert resp.json()["items"] == []

    finally:
        resp = await client.delete(f"/api/conversations/{conv_id}")
        assert resp.status_code == 204


async def test_get_nonexistent_conversation(client):
    resp = await client.get("/api/conversations/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
