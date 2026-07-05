"""Tests for the agent-management ("meta") tools and the server-side enforcement guard."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.services.autonomous_execution import ToolExecutionResult
from app.tools.create_agent import CreateAgentTool
from app.tools.create_workflow import CreateWorkflowTool


class _FakeSession:
    """Async context manager standing in for app.dependencies.async_session()."""

    async def __aenter__(self):
        return SimpleNamespace()

    async def __aexit__(self, *exc):
        return False


def _fake_async_session():
    return _FakeSession()


async def test_create_agent_success_reports_id():
    fake_resp = SimpleNamespace(id="11111111-1111-1111-1111-111111111111", name="Researcher")
    with (
        patch("app.tools.create_agent.async_session", _fake_async_session),
        patch("app.api.agents.create_agent", AsyncMock(return_value=fake_resp)) as endpoint,
    ):
        result = await CreateAgentTool().execute(
            caller_agent_id="caller-1",
            name="Researcher",
            system_prompt="You research things.",
            is_main=True,  # must be stripped
        )

    assert result.success is True
    assert result.metadata["agent_id"] == str(fake_resp.id)
    # is_main must never reach the endpoint body.
    body = endpoint.call_args.args[0]
    assert getattr(body, "is_main", False) is False


async def test_create_agent_converts_http_exception():
    with (
        patch("app.tools.create_agent.async_session", _fake_async_session),
        patch("app.api.agents.create_agent", AsyncMock(side_effect=HTTPException(409, "duplicate name"))),
    ):
        result = await CreateAgentTool().execute(name="Dup", system_prompt="x")

    assert result.success is False
    assert "409" in result.error
    assert "duplicate name" in result.error


async def test_create_agent_invalid_params_returns_error():
    # Missing required system_prompt → pydantic validation error, no endpoint call.
    result = await CreateAgentTool().execute(name="OnlyName")
    assert result.success is False
    assert "Invalid agent parameters" in result.error


async def test_create_workflow_defaults_step_agent_to_caller():
    captured = {}

    async def fake_endpoint(body, db=None):
        captured["steps"] = body.steps
        return SimpleNamespace(id="wf-1", name=body.name, steps=body.steps)

    with (
        patch("app.tools.create_workflow.async_session", _fake_async_session),
        patch("app.api.workflows.create_workflow", fake_endpoint),
    ):
        result = await CreateWorkflowTool().execute(
            caller_agent_id="caller-9",
            name="Solo",
            steps=[{"instructions": "do the thing"}],  # no agent_id → defaults to caller
        )

    assert result.success is True
    assert captured["steps"][0].agent_id == "caller-9"


async def test_create_workflow_requires_a_step():
    result = await CreateWorkflowTool().execute(caller_agent_id="c", name="Empty", steps=[])
    assert result.success is False
    assert "At least one step" in result.error


@pytest.mark.parametrize("tool_name", ["create_agent", "secret_admin_tool"])
async def test_chat_guard_blocks_tools_without_policy(tool_name):
    """A tool with no policy (not granted to the agent) is rejected and never executed."""
    from app.services.chat_execution import InteractiveToolExecutor

    executor = InteractiveToolExecutor(
        websocket=SimpleNamespace(),
        conversation_id="conv-1",
        agent=SimpleNamespace(id="agent-1", auto_approve=False),
        tool_slot_bindings={},
        credential_pool={},
        incoming=None,
        trace=SimpleNamespace(),
        persist_message=AsyncMock(),
    )

    tc = {"id": "tc-1", "name": tool_name, "arguments": {}}
    with patch("app.services.chat_execution.execute_tool", AsyncMock()) as exec_mock:
        result = await executor.handle_tool_call(tc, tool_policy=None)

    assert isinstance(result, ToolExecutionResult)
    assert result.success is False
    assert result.error == "Tool not permitted"
    exec_mock.assert_not_called()


async def test_chat_guard_allows_delegate_task_without_policy():
    """delegate_task is intentionally exempt from the guard (handled specially)."""
    from app.services.chat_execution import InteractiveToolExecutor

    executor = InteractiveToolExecutor(
        websocket=SimpleNamespace(),
        conversation_id="conv-1",
        agent=SimpleNamespace(id="agent-1", auto_approve=False),
        tool_slot_bindings={},
        credential_pool={},
        incoming=None,
        trace=SimpleNamespace(),
        persist_message=AsyncMock(),
    )

    tc = {"id": "tc-1", "name": "delegate_task", "arguments": {"agent_name": "x", "task": "y"}}
    sentinel = ToolExecutionResult(output="delegated", success=True)
    with patch.object(executor, "_run_delegation", AsyncMock(return_value=sentinel)) as deleg:
        result = await executor.handle_tool_call(tc, tool_policy=None)

    deleg.assert_awaited_once()
    assert result is sentinel
