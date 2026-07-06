"""Integration tests for the telegram-users access-control CRUD API."""

# > 2^53: proves telegram_id survives the JSON round-trip only because it is serialized as a string.
BIG_ID = "9007199254740993123"
GROUP_ID = "-1001234567890123"  # negative: Telegram group/channel id


async def test_telegram_user_lifecycle(client):
    """Create, list (pending-first ordering), update, then delete."""
    resp = await client.post(
        "/api/telegram-users",
        json={
            "telegram_id": BIG_ID,
            "username": "bigid_user",
            "note": "ops laptop",
        },
    )
    assert resp.status_code == 201
    user = resp.json()
    user_id = user["id"]
    pending_id = None
    try:
        # Admin-added ids are pre-approved with chat/receive defaults.
        assert user["telegram_id"] == BIG_ID
        assert user["status"] == "active"
        assert user["can_chat"] is True
        assert user["can_receive"] is True
        assert user["can_approve"] is False
        assert user["daily_budget_usd"] is None
        assert user["note"] == "ops laptop"

        # A pending row created later still sorts before the earlier active row.
        resp = await client.post(
            "/api/telegram-users",
            json={
                "telegram_id": 424242,
                "status": "pending",
            },
        )
        assert resp.status_code == 201
        pending_id = resp.json()["id"]

        resp = await client.get("/api/telegram-users")
        assert resp.status_code == 200
        ids = [u["id"] for u in resp.json()]
        assert ids.index(pending_id) < ids.index(user_id)

        # Update toggles permissions and status.
        resp = await client.put(
            f"/api/telegram-users/{user_id}",
            json={
                "status": "blocked",
                "can_chat": False,
                "can_approve": True,
                "daily_budget_usd": 2.5,
                "note": "suspended",
            },
        )
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["status"] == "blocked"
        assert updated["can_chat"] is False
        assert updated["can_approve"] is True
        assert updated["daily_budget_usd"] == 2.5
        assert updated["note"] == "suspended"
        assert updated["telegram_id"] == BIG_ID  # unchanged by partial update

        # Delete, then the row is gone.
        resp = await client.delete(f"/api/telegram-users/{user_id}")
        assert resp.status_code == 204
        user_id = None
        resp = await client.get("/api/telegram-users")
        assert all(u["telegram_id"] != BIG_ID for u in resp.json())
    finally:
        if user_id:
            await client.delete(f"/api/telegram-users/{user_id}")
        if pending_id:
            await client.delete(f"/api/telegram-users/{pending_id}")


async def test_negative_telegram_id(client):
    """Group/channel ids are negative and must round-trip as strings too."""
    resp = await client.post("/api/telegram-users", json={"telegram_id": GROUP_ID, "note": "family group"})
    assert resp.status_code == 201
    user_id = resp.json()["id"]
    try:
        assert resp.json()["telegram_id"] == GROUP_ID
    finally:
        await client.delete(f"/api/telegram-users/{user_id}")


async def test_duplicate_telegram_id_conflict(client):
    resp = await client.post("/api/telegram-users", json={"telegram_id": 777001})
    assert resp.status_code == 201
    user_id = resp.json()["id"]
    try:
        # Same id again — as int and as string — is rejected.
        resp = await client.post("/api/telegram-users", json={"telegram_id": 777001})
        assert resp.status_code == 409
        resp = await client.post("/api/telegram-users", json={"telegram_id": "777001"})
        assert resp.status_code == 409
    finally:
        await client.delete(f"/api/telegram-users/{user_id}")


async def test_invalid_telegram_id_rejected(client):
    for bad in ["abc", "12ab34", "--123", "-", "", "1.5"]:
        resp = await client.post("/api/telegram-users", json={"telegram_id": bad})
        assert resp.status_code == 422, f"expected 422 for {bad!r}"


async def test_invalid_status_rejected(client):
    resp = await client.post("/api/telegram-users", json={"telegram_id": 777002, "status": "banned"})
    assert resp.status_code == 422


async def test_negative_budget_rejected(client):
    resp = await client.post("/api/telegram-users", json={"telegram_id": 777003, "daily_budget_usd": -1})
    assert resp.status_code == 422

    # Same guard on update.
    resp = await client.post("/api/telegram-users", json={"telegram_id": 777003})
    assert resp.status_code == 201
    user_id = resp.json()["id"]
    try:
        resp = await client.put(f"/api/telegram-users/{user_id}", json={"daily_budget_usd": -0.5})
        assert resp.status_code == 422
    finally:
        await client.delete(f"/api/telegram-users/{user_id}")


async def test_update_nonexistent_returns_404(client):
    resp = await client.put("/api/telegram-users/00000000-0000-0000-0000-000000000000", json={"status": "active"})
    assert resp.status_code == 404


async def test_delete_nonexistent_returns_404(client):
    resp = await client.delete("/api/telegram-users/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
