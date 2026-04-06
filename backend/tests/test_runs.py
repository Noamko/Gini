"""Tests for run status helpers."""

from app.api.runs import _failed_terminal_step
from app.services.agent_orchestrator import _failed_terminal_step as _delegation_failed_terminal_step


def test_failed_terminal_step_returns_last_failed_tool_call():
    steps = [
        {"type": "thinking", "content": "planning"},
        {"type": "tool_call", "tool": "read_email_imap", "success": True},
        {"type": "tool_call", "tool": "send_email_smtp", "success": False, "error": "smtp failed"},
        {"type": "assistant", "content": "The send failed."},
    ]

    failed = _failed_terminal_step(steps)

    assert failed is not None
    assert failed["tool"] == "send_email_smtp"
    assert failed["error"] == "smtp failed"


def test_failed_terminal_step_ignores_successful_tool_calls():
    steps = [
        {"type": "tool_call", "tool": "read_email_imap", "success": True},
        {"type": "assistant", "content": "Done"},
    ]

    assert _failed_terminal_step(steps) is None


def test_failed_terminal_step_ignores_earlier_failure_if_last_tool_succeeds():
    steps = [
        {"type": "tool_call", "tool": "send_email_smtp", "success": False, "error": "rejected"},
        {"type": "assistant", "content": "Trying a different path"},
        {"type": "tool_call", "tool": "read_email_imap", "success": True},
        {"type": "assistant", "content": "Done"},
    ]

    assert _failed_terminal_step(steps) is None


def test_delegation_failed_terminal_step_matches_run_behavior():
    steps = [
        {"type": "tool_call", "tool": "send_email_smtp", "success": False, "error": "rejected"},
        {"type": "assistant", "content": "done"},
    ]

    failed = _delegation_failed_terminal_step(steps)

    assert failed is not None
    assert failed["tool"] == "send_email_smtp"
