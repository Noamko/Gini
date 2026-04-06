"""Integration tests for the credentials API."""


async def test_credential_reveal_is_disabled(client):
    resp = await client.post("/api/credentials", json={
        "name": "test-disabled-reveal",
        "value": "secret-value",
    })
    assert resp.status_code == 201
    credential_id = resp.json()["id"]

    try:
        resp = await client.get(f"/api/credentials/{credential_id}/reveal")
        assert resp.status_code == 403
        assert "disabled" in resp.json()["detail"].lower()
    finally:
        await client.delete(f"/api/credentials/{credential_id}")
