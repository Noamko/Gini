"""DB-backed Telegram access-control tests. No real Telegram/network calls anywhere."""

from uuid import uuid4

import httpx
from sqlalchemy import delete, select

from app.config import settings
from app.dependencies import redis_client
from app.models.telegram_user import TelegramUser
from app.services.telegram_bot import PENDING_ACCESS_REPLY, TelegramBot
from app.tools.send_telegram import _broadcast


def _unique_tid() -> int:
    return uuid4().int % 10**12


def _message(tid: int, **sender_extra) -> dict:
    return {"chat": {"id": tid}, "from": {"id": tid, **sender_extra}, "text": "hello"}


def _bot_with_capture(monkeypatch) -> tuple[TelegramBot, list[tuple[int, str]]]:
    bot = TelegramBot()
    sent: list[tuple[int, str]] = []

    async def fake_send(chat_id, text, reply_markup=None):
        sent.append((chat_id, text))

    monkeypatch.setattr(bot, "_send_message", fake_send)
    return bot, sent


async def _cleanup(db_session, *tids: int):
    await db_session.execute(delete(TelegramUser).where(TelegramUser.telegram_id.in_(tids)))
    await db_session.commit()


# ── _gate_message: access helper matrix ─────────────────────────────


async def test_gate_allows_active_can_chat(db_session, monkeypatch):
    tid = _unique_tid()
    row = TelegramUser(telegram_id=tid, status="active", can_chat=True)
    db_session.add(row)
    await db_session.commit()

    bot, sent = _bot_with_capture(monkeypatch)
    try:
        user = await bot._gate_message(_message(tid))
        assert user is not None
        assert user.telegram_id == tid
        assert sent == []  # allowed senders get no gate reply

        await db_session.refresh(row)
        assert row.last_seen_at is not None  # active senders get a last-seen bump
    finally:
        await _cleanup(db_session, tid)


async def test_gate_denies_pending_with_reply(db_session, monkeypatch):
    tid = _unique_tid()
    row = TelegramUser(telegram_id=tid, status="pending")
    db_session.add(row)
    await db_session.commit()

    bot, sent = _bot_with_capture(monkeypatch)
    try:
        user = await bot._gate_message(_message(tid))
        assert user is None
        assert sent == [(tid, PENDING_ACCESS_REPLY)]

        await db_session.refresh(row)
        assert row.last_seen_at is not None
    finally:
        await _cleanup(db_session, tid)


async def test_gate_denies_blocked_silently(db_session, monkeypatch):
    tid = _unique_tid()
    row = TelegramUser(telegram_id=tid, status="blocked", can_chat=True)
    db_session.add(row)
    await db_session.commit()

    bot, sent = _bot_with_capture(monkeypatch)
    try:
        user = await bot._gate_message(_message(tid))
        assert user is None
        assert sent == []  # blocked senders get silence

        await db_session.refresh(row)
        assert row.last_seen_at is not None
    finally:
        await _cleanup(db_session, tid)


async def test_gate_denies_active_without_can_chat(db_session, monkeypatch):
    tid = _unique_tid()
    db_session.add(TelegramUser(telegram_id=tid, status="active", can_chat=False))
    await db_session.commit()

    bot, sent = _bot_with_capture(monkeypatch)
    try:
        user = await bot._gate_message(_message(tid))
        assert user is None
        assert sent == []
    finally:
        await _cleanup(db_session, tid)


async def test_unknown_sender_auto_registered_pending(db_session, monkeypatch):
    tid = _unique_tid()
    bot, sent = _bot_with_capture(monkeypatch)
    try:
        user = await bot._gate_message(_message(tid, username="newbie", first_name="New", last_name="Bee"))
        assert user is None
        assert sent == [(tid, PENDING_ACCESS_REPLY)]

        result = await db_session.execute(select(TelegramUser).where(TelegramUser.telegram_id == tid))
        row = result.scalar_one()
        assert row.status == "pending"
        assert row.can_chat is False
        assert row.username == "newbie"
        assert row.first_name == "New"
        assert row.last_name == "Bee"
        assert row.last_seen_at is not None
    finally:
        await _cleanup(db_session, tid)


# ── _bootstrap_allowed_users: env seeding ───────────────────────────


async def test_bootstrap_skips_malformed_tokens(db_session, monkeypatch):
    tid_a, tid_b = _unique_tid(), _unique_tid()
    monkeypatch.setattr(settings, "telegram_allowed_users", f"{tid_a}, not-a-number, {tid_b}")
    try:
        await TelegramBot()._bootstrap_allowed_users()

        result = await db_session.execute(select(TelegramUser).where(TelegramUser.telegram_id.in_([tid_a, tid_b])))
        rows = {r.telegram_id: r for r in result.scalars()}
        assert set(rows) == {tid_a, tid_b}  # one bad token must not lock out the others
        assert all(r.status == "active" and r.can_chat and r.can_receive and r.can_approve for r in rows.values())
    finally:
        await _cleanup(db_session, tid_a, tid_b)


async def test_bootstrap_preserves_existing_rows(db_session, monkeypatch):
    tid = _unique_tid()
    db_session.add(TelegramUser(telegram_id=tid, status="blocked"))
    await db_session.commit()
    monkeypatch.setattr(settings, "telegram_allowed_users", str(tid))
    try:
        await TelegramBot()._bootstrap_allowed_users()

        result = await db_session.execute(select(TelegramUser).where(TelegramUser.telegram_id == tid))
        assert result.scalar_one().status == "blocked"  # env must not resurrect a blocked id
    finally:
        await _cleanup(db_session, tid)


# ── _budget_refusal: daily spend gate ───────────────────────────────


async def test_budget_refusal():
    tid = _unique_tid()
    bot = TelegramBot()
    limited = TelegramUser(telegram_id=tid, status="active", daily_budget_usd=1.0)
    try:
        assert await bot._budget_refusal(None) is None
        assert await bot._budget_refusal(TelegramUser(telegram_id=tid, daily_budget_usd=None)) is None
        assert await bot._budget_refusal(limited) is None  # nothing spent yet

        await bot._record_spend(tid, 2.5)
        refusal = await bot._budget_refusal(limited)
        assert refusal is not None
        assert "daily budget" in refusal
    finally:
        await redis_client.delete(bot._spend_key(tid))


# ── _send_approval_request: buttons only for approvers ──────────────


def _bot_with_markup_capture(monkeypatch) -> tuple[TelegramBot, list[tuple[int, str, dict | None]]]:
    bot = TelegramBot()
    sent: list[tuple[int, str, dict | None]] = []

    async def fake_send(chat_id, text, reply_markup=None):
        sent.append((chat_id, text, reply_markup))

    monkeypatch.setattr(bot, "_send_message", fake_send)
    return bot, sent


async def test_approval_request_without_can_approve_has_no_buttons(db_session, monkeypatch):
    tid = _unique_tid()
    db_session.add(TelegramUser(telegram_id=tid, status="active", can_chat=True, can_approve=False))
    await db_session.commit()

    bot, sent = _bot_with_markup_capture(monkeypatch)
    try:
        await bot._send_approval_request(tid, {"id": "ap-1", "tool_name": "create_agent", "arguments": {}})
        assert len(sent) == 1
        assert sent[0][2] is None  # no inline keyboard
        assert "requires approval from an operator" in sent[0][1]
    finally:
        await _cleanup(db_session, tid)


async def test_approval_request_with_can_approve_has_buttons(db_session, monkeypatch):
    tid = _unique_tid()
    db_session.add(TelegramUser(telegram_id=tid, status="active", can_approve=True))
    await db_session.commit()

    bot, sent = _bot_with_markup_capture(monkeypatch)
    try:
        await bot._send_approval_request(tid, {"id": "ap-2", "tool_name": "create_agent", "arguments": {}})
        assert len(sent) == 1
        markup = sent[0][2]
        assert markup is not None
        assert markup["inline_keyboard"][0][0]["callback_data"] == "approval:approve:ap-2"
    finally:
        await _cleanup(db_session, tid)


# ── _handle_callback_query: can_approve gating ──────────────────────


def _callback(tid: int, data: str) -> dict:
    return {"id": "cb-test", "from": {"id": tid}, "data": data}


def _bot_with_callback_capture(monkeypatch) -> tuple[TelegramBot, list[str]]:
    bot = TelegramBot()
    answers: list[str] = []

    async def fake_answer(callback_query_id, text, show_alert=False):
        answers.append(text)

    monkeypatch.setattr(bot, "_answer_callback_query", fake_answer)
    return bot, answers


async def test_callback_denied_without_can_approve(db_session, monkeypatch):
    tid = _unique_tid()
    db_session.add(TelegramUser(telegram_id=tid, status="active", can_chat=True, can_approve=False))
    await db_session.commit()

    bot, answers = _bot_with_callback_capture(monkeypatch)
    try:
        await bot._handle_callback_query(_callback(tid, "approval:approve:some-id"))
        assert answers == ["You are not authorized to approve actions."]
    finally:
        await _cleanup(db_session, tid)


async def test_callback_gate_passes_for_approver(db_session, monkeypatch):
    tid = _unique_tid()
    db_session.add(TelegramUser(telegram_id=tid, status="active", can_approve=True))
    await db_session.commit()

    bot, answers = _bot_with_callback_capture(monkeypatch)
    try:
        # Non-approval payload: reaching "Unsupported action." proves the gate passed.
        await bot._handle_callback_query(_callback(tid, "noop"))
        assert answers == ["Unsupported action."]
    finally:
        await _cleanup(db_session, tid)


async def test_unknown_callback_presser_denied_and_not_registered(db_session, monkeypatch):
    tid = _unique_tid()
    bot, answers = _bot_with_callback_capture(monkeypatch)

    await bot._handle_callback_query(_callback(tid, "approval:approve:some-id"))
    assert answers == ["You are not authorized to approve actions."]

    result = await db_session.execute(select(TelegramUser).where(TelegramUser.telegram_id == tid))
    assert result.scalar_one_or_none() is None  # callbacks must not create pending rows


# ── _broadcast: can_receive enforcement ─────────────────────────────


async def test_broadcast_skips_registered_not_permitted(db_session, monkeypatch):
    refused_tid = _unique_tid()  # registered, can_receive off
    blocked_tid = _unique_tid()  # registered, status blocked
    allowed_tid = _unique_tid()  # registered, active + can_receive
    unknown_tid = _unique_tid()  # no row — stays allowed
    db_session.add(TelegramUser(telegram_id=refused_tid, status="active", can_receive=False))
    db_session.add(TelegramUser(telegram_id=blocked_tid, status="blocked", can_receive=True))
    db_session.add(TelegramUser(telegram_id=allowed_tid, status="active", can_receive=True))
    await db_session.commit()

    attempted: list[str] = []

    class FakeResponse:
        def json(self):
            return {"ok": True, "result": {"message_id": 1}}

    async def fake_post(self, url, json=None):
        attempted.append(json["chat_id"])
        return FakeResponse()

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    try:
        result = await _broadcast(
            token="test-token",
            targets=[str(refused_tid), str(blocked_tid), str(allowed_tid), str(unknown_tid)],
            path="sendMessage",
            payload_for=lambda cid: {"chat_id": cid, "text": "hi"},
            timeout=5,
            summary=lambda s: f"sent to {len(s)} chat(s)",
        )
        assert attempted == [str(allowed_tid), str(unknown_tid)]
        assert result.success is True
        assert result.metadata["chat_ids"] == [str(allowed_tid), str(unknown_tid)]
        assert result.metadata["failures"] == {
            str(refused_tid): f"recipient {refused_tid} not permitted",
            str(blocked_tid): f"recipient {blocked_tid} not permitted",
        }
        assert f"recipient {refused_tid} not permitted" in result.output
    finally:
        await _cleanup(db_session, refused_tid, blocked_tid, allowed_tid, unknown_tid)


async def test_broadcast_fails_when_all_targets_refused(db_session, monkeypatch):
    tid = _unique_tid()
    db_session.add(TelegramUser(telegram_id=tid, status="active", can_receive=False))
    await db_session.commit()

    async def fake_post(self, url, json=None):
        raise AssertionError("no HTTP send expected for refused recipients")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    try:
        result = await _broadcast(
            token="test-token",
            targets=[str(tid)],
            path="sendMessage",
            payload_for=lambda cid: {"chat_id": cid, "text": "hi"},
            timeout=5,
            summary=lambda s: f"sent to {len(s)} chat(s)",
        )
        assert result.success is False
        assert f"recipient {tid} not permitted" in (result.error or "")
    finally:
        await _cleanup(db_session, tid)
