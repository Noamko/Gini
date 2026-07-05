import uuid
from types import SimpleNamespace

from app.services.execution_prep import (
    _tool_grants_for_agent,
    prepare_autonomous_resources,
    prepare_chat_resources,
)
from app.services.tool_catalog import ToolPolicy


def _policy(name: str, *, requires_approval: bool = False) -> ToolPolicy:
    return ToolPolicy(
        name=name,
        description=f"{name} desc",
        input_schema={"type": "object"},
        requires_sandbox=False,
        requires_approval=requires_approval,
        is_builtin=True,
    )


def _patch_grants(monkeypatch, *, skill_tool_names, tool_grants=None):
    async def fake_skill_names(_agent_id):
        return set(skill_tool_names)

    async def fake_tool_grants(_agent_id):
        return dict(tool_grants or {})

    async def fake_credential_pool(_agent_id):
        return {}

    monkeypatch.setattr("app.services.execution_prep.get_agent_skill_tool_names", fake_skill_names)
    monkeypatch.setattr("app.services.execution_prep.get_agent_tool_grants", fake_tool_grants)
    monkeypatch.setattr("app.services.execution_prep.get_agent_credential_pool", fake_credential_pool)


def _patch_list_policies(monkeypatch, main_tools):
    optin_names = {"create_agent"}

    async def fake_list_tool_policies(**kwargs):
        allowed = kwargs.get("allowed_tool_names")
        optin = kwargs.get("optin_tool_names")
        result = []
        for p in main_tools:
            if p.name in optin_names:
                if optin and p.name in optin:
                    result.append(p)
            elif allowed is None or p.name in allowed:
                result.append(p)
        return result

    monkeypatch.setattr("app.services.execution_prep.list_tool_policies", fake_list_tool_policies)


def _agent(**kwargs):
    kwargs.setdefault("id", uuid.uuid4())
    kwargs.setdefault("system_prompt", "sp")
    kwargs.setdefault("metadata_", {})
    kwargs.setdefault("auto_approve", False)
    return SimpleNamespace(**kwargs)


async def test_prepare_chat_resources_filters_optin(monkeypatch):
    _patch_list_policies(monkeypatch, [_policy("read_file"), _policy("create_agent")])
    _patch_grants(monkeypatch, skill_tool_names={"read_file", "create_agent"})

    resources = await prepare_chat_resources(_agent(auto_approve=True))
    assert {p.name for p in resources.tool_policies} == {"read_file", "create_agent"}
    # Credentials are no longer a flat dict on resources; per-tool slots are resolved at call time.
    assert resources.credential_pool == {}
    assert resources.tool_slot_bindings == {}


async def test_prepare_autonomous_resources_dispatcher_keeps_full_catalog(monkeypatch):
    _patch_list_policies(monkeypatch, [_policy("read_file"), _policy("run_shell")])
    _patch_grants(monkeypatch, skill_tool_names=set())

    agent = _agent(metadata_={"role": "dispatcher"})
    resources = await prepare_autonomous_resources(agent)
    assert {p.name for p in resources.tool_policies} == {"read_file", "run_shell"}


async def test_tool_grants_for_agent_specialist_restricts(monkeypatch):
    _patch_grants(monkeypatch, skill_tool_names={"read_file"})
    allowed, optin = await _tool_grants_for_agent(_agent())
    assert allowed == {"read_file"}
    assert optin == set()


async def test_tool_grants_for_agent_optin_only(monkeypatch):
    _patch_grants(monkeypatch, skill_tool_names={"create_agent"})
    allowed, optin = await _tool_grants_for_agent(_agent())
    assert allowed is None
    assert optin == {"create_agent"}


async def test_tool_grants_for_agent_specialist_with_optin(monkeypatch):
    _patch_grants(monkeypatch, skill_tool_names={"read_file", "create_agent"})
    allowed, optin = await _tool_grants_for_agent(_agent())
    assert allowed == {"read_file"}
    assert optin == {"create_agent"}


async def test_tool_grants_for_agent_unions_direct_grants(monkeypatch):
    # A tool granted directly (not via a skill) is included in the effective set.
    _patch_grants(monkeypatch, skill_tool_names=set(), tool_grants={"send_email_smtp": {}})
    allowed, optin = await _tool_grants_for_agent(_agent())
    assert allowed == {"send_email_smtp"}
    assert optin == set()


async def test_tool_grants_for_agent_no_grants_returns_full(monkeypatch):
    _patch_grants(monkeypatch, skill_tool_names=set())
    allowed, optin = await _tool_grants_for_agent(_agent())
    assert allowed is None
    assert optin == set()
