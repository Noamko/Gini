"""Tests for execution resource preparation."""
from types import SimpleNamespace

from app.services.execution_prep import prepare_autonomous_resources, prepare_chat_resources
from app.services.tool_catalog import ToolPolicy


async def test_prepare_chat_resources_uses_interactive_prompt_and_all_tools(monkeypatch):
    agent = SimpleNamespace(id="agent-0", auto_approve=False, metadata_={"role": "dispatcher"})
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

    async def fake_list_tool_policies(*, include_approval_tools: bool, allowed_tool_names=None):
        calls["include_approval_tools"] = include_approval_tools
        calls["allowed_tool_names"] = allowed_tool_names
        return policies

    async def fake_get_agent_skill_tool_names(_agent_id):
        return set()

    async def fake_get_agent_credentials(_agent_id):
        calls["credentials"] = True
        return {"imap_password": "secret"}

    monkeypatch.setattr("app.services.execution_prep.get_assembled_prompt", fake_get_assembled_prompt)
    monkeypatch.setattr("app.services.execution_prep.list_tool_policies", fake_list_tool_policies)
    monkeypatch.setattr("app.services.execution_prep.get_agent_skill_tool_names", fake_get_agent_skill_tool_names)
    monkeypatch.setattr("app.services.execution_prep.get_agent_credentials", fake_get_agent_credentials)

    resources = await prepare_chat_resources(agent)

    assert calls == {
        "prompt": "standard",
        "credentials": True,
        "include_approval_tools": True,
        "allowed_tool_names": None,
    }
    assert resources.system_prompt == "chat prompt"
    assert resources.tool_policy_by_name["approval_tool"].requires_approval is True
    assert resources.tool_specs == [policy.to_llm_spec() for policy in policies]
    assert resources.credentials == {"imap_password": "secret"}


async def test_prepare_autonomous_resources_respects_agent_trust(monkeypatch):
    agent = SimpleNamespace(id="agent-0", auto_approve=False, metadata_={"role": "dispatcher"})
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

    async def fake_list_tool_policies(*, include_approval_tools: bool, allowed_tool_names=None):
        calls["include_approval_tools"] = include_approval_tools
        calls["allowed_tool_names"] = allowed_tool_names
        return policies

    async def fake_get_agent_skill_tool_names(_agent_id):
        return set()

    async def fake_get_agent_credentials(_agent_id):
        calls["credentials"] = True
        return {"token": "secret"}

    monkeypatch.setattr("app.services.execution_prep.get_autonomous_prompt", fake_get_autonomous_prompt)
    monkeypatch.setattr("app.services.execution_prep.list_tool_policies", fake_list_tool_policies)
    monkeypatch.setattr("app.services.execution_prep.get_agent_skill_tool_names", fake_get_agent_skill_tool_names)
    monkeypatch.setattr("app.services.execution_prep.get_agent_credentials", fake_get_agent_credentials)

    resources = await prepare_autonomous_resources(agent)

    assert calls == {
        "prompt": "autonomous",
        "credentials": True,
        "include_approval_tools": False,
        "allowed_tool_names": None,
    }
    assert resources.system_prompt == "autonomous prompt"
    assert resources.tool_policy_by_name == {"safe_tool": policies[0]}
    assert resources.credentials == {"token": "secret"}


async def test_prepare_autonomous_resources_can_include_approval_tools(monkeypatch):
    agent = SimpleNamespace(id="agent-0", auto_approve=False, metadata_={"role": "dispatcher"})
    calls: dict[str, object] = {}

    async def fake_get_autonomous_prompt(_agent):
        return "autonomous prompt"

    async def fake_list_tool_policies(*, include_approval_tools: bool, allowed_tool_names=None):
        calls["include_approval_tools"] = include_approval_tools
        calls["allowed_tool_names"] = allowed_tool_names
        return []

    async def fake_get_agent_skill_tool_names(_agent_id):
        return set()

    async def fake_get_agent_credentials(_agent_id):
        return {}

    monkeypatch.setattr("app.services.execution_prep.get_autonomous_prompt", fake_get_autonomous_prompt)
    monkeypatch.setattr("app.services.execution_prep.list_tool_policies", fake_list_tool_policies)
    monkeypatch.setattr("app.services.execution_prep.get_agent_skill_tool_names", fake_get_agent_skill_tool_names)
    monkeypatch.setattr("app.services.execution_prep.get_agent_credentials", fake_get_agent_credentials)

    await prepare_autonomous_resources(agent, include_approval_tools=True)

    assert calls == {
        "include_approval_tools": True,
        "allowed_tool_names": None,
    }


async def test_prepare_chat_resources_filters_specialist_tools_to_skill_links(monkeypatch):
    agent = SimpleNamespace(
        id="agent-1",
        auto_approve=False,
        metadata_={"role": "notification"},
    )
    calls: dict[str, object] = {}
    policies = [
        ToolPolicy(
            name="send_telegram",
            description="Telegram",
            input_schema={"type": "object"},
            requires_sandbox=False,
            requires_approval=False,
            is_builtin=False,
        ),
    ]

    async def fake_get_assembled_prompt(_agent):
        return "chat prompt"

    async def fake_get_agent_skill_tool_names(_agent_id):
        return {"send_telegram", "send_telegram_photo"}

    async def fake_get_agent_credentials(_agent_id):
        return {"Telegram Bot Token": "secret"}

    async def fake_list_tool_policies(*, include_approval_tools: bool, allowed_tool_names=None):
        calls["include_approval_tools"] = include_approval_tools
        calls["allowed_tool_names"] = allowed_tool_names
        return policies

    monkeypatch.setattr("app.services.execution_prep.get_assembled_prompt", fake_get_assembled_prompt)
    monkeypatch.setattr("app.services.execution_prep.get_agent_skill_tool_names", fake_get_agent_skill_tool_names)
    monkeypatch.setattr("app.services.execution_prep.get_agent_credentials", fake_get_agent_credentials)
    monkeypatch.setattr("app.services.execution_prep.list_tool_policies", fake_list_tool_policies)

    resources = await prepare_chat_resources(agent)

    assert calls == {
        "include_approval_tools": True,
        "allowed_tool_names": {"send_telegram", "send_telegram_photo"},
    }
    assert resources.tool_policy_by_name == {"send_telegram": policies[0]}
    assert resources.credentials == {"Telegram Bot Token": "secret"}
