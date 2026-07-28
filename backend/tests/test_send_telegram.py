"""Tests for send_telegram chat_id resolution — explicit ids must never silently reroute."""

import pytest

from app.tools.send_telegram import SendTelegramTool, _resolve_chat_ids

BOUND = {"chat_id": ["111", "222"]}


def test_numeric_chat_id_targets_only_that_chat():
    targets, error = _resolve_chat_ids("999888777", BOUND)
    assert error is None
    assert targets == ["999888777"]


def test_negative_group_id_is_numeric():
    targets, error = _resolve_chat_ids("-100123", BOUND)
    assert error is None
    assert targets == ["-100123"]


def test_omitted_chat_id_broadcasts_to_all_bound():
    targets, error = _resolve_chat_ids(None, BOUND)
    assert error is None
    assert targets == ["111", "222"]


def test_single_bound_value_not_in_list():
    targets, error = _resolve_chat_ids(None, {"chat_id": "111"})
    assert error is None
    assert targets == ["111"]


def test_non_numeric_chat_id_errors_instead_of_falling_back():
    # Regression: a credential *name* as chat_id used to silently broadcast to the
    # bound chats, delivering to the wrong recipients.
    targets, error = _resolve_chat_ids("Tom telegram account", BOUND)
    assert targets == []
    assert error is not None
    assert "not a numeric" in error


def test_no_chat_id_and_no_binding_errors():
    targets, error = _resolve_chat_ids(None, {})
    assert targets == []
    assert error is not None
    assert "no chat credential" in error


@pytest.mark.asyncio
async def test_execute_reports_non_numeric_chat_id(monkeypatch):
    monkeypatch.setattr("app.tools.send_telegram.settings.telegram_bot_token", "123:abc")
    tool = SendTelegramTool()
    result = await tool.execute(text="hi", chat_id="Tom telegram account", credential_values=BOUND)
    assert result.success is False
    assert "not a numeric" in (result.error or "")
