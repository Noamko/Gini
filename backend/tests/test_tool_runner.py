"""Tests for tool_runner credential injection and sandbox env mapping."""

import pytest

from app.services import tool_runner


@pytest.mark.asyncio
async def test_run_shell_exposes_bound_credentials_as_env(monkeypatch):
    captured = {}

    class FakeSandboxResult:
        success = True
        output = "done"
        exit_code = 0

    async def fake_execute(command, timeout, allow_network, env):
        captured["env"] = env
        return FakeSandboxResult()

    monkeypatch.setattr(tool_runner.sandbox_manager, "execute", fake_execute)

    # credential_values is the tool's already-scoped slot dict ({binding_name: value}).
    result = await tool_runner.execute_tool(
        "run_shell",
        {"command": "echo hi"},
        use_sandbox=True,
        allow_network=False,
        credential_values={"Telegram Bot Token": "secret-token"},
    )

    assert result.success is True
    assert captured["env"] == {"GINI_CRED_TELEGRAM_BOT_TOKEN": "secret-token"}


@pytest.mark.asyncio
async def test_run_shell_with_no_credentials_has_empty_env(monkeypatch):
    captured = {}

    class FakeSandboxResult:
        success = True
        output = "done"
        exit_code = 0

    async def fake_execute(command, timeout, allow_network, env):
        captured["env"] = env
        return FakeSandboxResult()

    monkeypatch.setattr(tool_runner.sandbox_manager, "execute", fake_execute)

    result = await tool_runner.execute_tool(
        "run_shell",
        {"command": "echo hi"},
        use_sandbox=True,
        allow_network=False,
        credential_values={},
    )

    assert result.success is True
    assert captured["env"] == {}
