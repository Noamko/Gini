"""Tests for execution resource preparation."""
from types import SimpleNamespace

from app.services.execution_prep import prepare_autonomous_resources, prepare_chat_resources
from app.services.tool_catalog import ToolPolicy


async def test_prepare_chat_resources_uses_interactive_prompt_and_all_tools(monkeypatch):
    agent = SimpleNamespace(auto_approve=False)
    calls: dict[str, object] = {}
    policies = [
        ToolPolicy(
            name="safe_tool",
            description="Safe tool",
            input_schema={"type": "object"},
            requires_sandbox=False,
            requires_approval=False,
            is_builtin=True,
        ),
        ToolPolicy(
            name="approval_tool",
            description="Approval tool",
            input_schema={"type": "object"},
            requires_sandbox=True,
            requires_approval=True,
            is_builtin=True,
        ),
    ]

    async def fake_get_assembled_prompt(_agent):
        calls["prompt"] = "standard"
        return "chat prompt"

    async def fake_get_assembled_prompt_with_credentials(_agent):
        calls["prompt"] = "credentials"
        return "credential prompt"

    async def fake_list_tool_policies(*, include_approval_tools: bool):
        calls["include_approval_tools"] = include_approval_tools
        return policies

    monkeypatch.setattr("app.services.execution_prep.get_assembled_prompt", fake_get_assembled_prompt)
    monkeypatch.setattr("app.services.execution_prep.get_assembled_prompt_with_credentials", fake_get_assembled_prompt_with_credentials)
    monkeypatch.setattr("app.services.execution_prep.list_tool_policies", fake_list_tool_policies)

    resources = await prepare_chat_resources(agent)

    assert calls == {"prompt": "standard", "include_approval_tools": True}
    assert resources.system_prompt == "chat prompt"
    assert resources.tool_policy_by_name["approval_tool"].requires_approval is True
    assert resources.tool_specs == [policy.to_llm_spec() for policy in policies]


async def test_prepare_autonomous_resources_respects_agent_trust(monkeypatch):
    agent = SimpleNamespace(auto_approve=False)
    calls: dict[str, object] = {}
    policies = [
        ToolPolicy(
            name="safe_tool",
            description="Safe tool",
            input_schema={"type": "object"},
            requires_sandbox=False,
            requires_approval=False,
            is_builtin=True,
        ),
    ]

    async def fake_get_autonomous_prompt(_agent):
        calls["prompt"] = "autonomous"
        return "autonomous prompt"

    async def fake_list_tool_policies(*, include_approval_tools: bool):
        calls["include_approval_tools"] = include_approval_tools
        return policies

    monkeypatch.setattr("app.services.execution_prep.get_autonomous_prompt", fake_get_autonomous_prompt)
    monkeypatch.setattr("app.services.execution_prep.list_tool_policies", fake_list_tool_policies)

    resources = await prepare_autonomous_resources(agent)

    assert calls == {"prompt": "autonomous", "include_approval_tools": False}
    assert resources.system_prompt == "autonomous prompt"
    assert resources.tool_policy_by_name == {"safe_tool": policies[0]}
