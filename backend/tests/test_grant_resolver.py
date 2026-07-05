"""Unit tests for per-tool credential scoping (no DB)."""

from app.services.grant_resolver import PooledCredential, resolve_tool_credentials
from app.tools.base import CredentialSlot


def _pool(*creds: PooledCredential) -> dict[str, PooledCredential]:
    return {c.id: c for c in creds}


def test_bound_slot_resolves_to_value():
    pool = _pool(
        PooledCredential(id="c1", name="Gmail", type="password", value="pw"),
        PooledCredential(id="c2", name="OpenAI", type="api_key", value="sk"),
    )
    resolved, missing = resolve_tool_credentials(
        declared_slots=[CredentialSlot(name="password", type="password")],
        open_credential_slots=False,
        slot_bindings={"password": "c1"},
        credential_pool=pool,
    )
    assert resolved == {"password": "pw"}
    assert missing == []


def test_only_bound_slot_is_returned_not_whole_pool():
    pool = _pool(
        PooledCredential(id="c1", name="Gmail", type="password", value="pw"),
        PooledCredential(id="c2", name="OpenAI", type="api_key", value="sk"),
    )
    resolved, _ = resolve_tool_credentials(
        declared_slots=[CredentialSlot(name="password", type="password")],
        open_credential_slots=False,
        slot_bindings={"password": "c1"},
        credential_pool=pool,
    )
    # The unrelated OpenAI secret must NOT leak into this tool.
    assert "sk" not in resolved.values()
    assert set(resolved) == {"password"}


def test_unique_type_match_auto_binds():
    pool = _pool(PooledCredential(id="c1", name="Gmail", type="password", value="pw"))
    resolved, missing = resolve_tool_credentials(
        declared_slots=[CredentialSlot(name="password", type="password")],
        open_credential_slots=False,
        slot_bindings={},
        credential_pool=pool,
    )
    assert resolved == {"password": "pw"}
    assert missing == []


def test_ambiguous_type_does_not_auto_bind_required_slot():
    pool = _pool(
        PooledCredential(id="c1", name="GmailA", type="password", value="a"),
        PooledCredential(id="c2", name="GmailB", type="password", value="b"),
    )
    resolved, missing = resolve_tool_credentials(
        declared_slots=[CredentialSlot(name="password", type="password", required=True)],
        open_credential_slots=False,
        slot_bindings={},
        credential_pool=pool,
    )
    assert resolved == {}
    assert missing == ["password"]


def test_optional_unbound_slot_is_not_missing():
    resolved, missing = resolve_tool_credentials(
        declared_slots=[CredentialSlot(name="chat_id", type="telegram", required=False)],
        open_credential_slots=False,
        slot_bindings={},
        credential_pool={},
    )
    assert resolved == {}
    assert missing == []


def test_multi_slot_binds_list_to_all_values():
    pool = _pool(
        PooledCredential(id="c1", name="ChatA", type="telegram", value="111"),
        PooledCredential(id="c2", name="ChatB", type="telegram", value="222"),
    )
    resolved, missing = resolve_tool_credentials(
        declared_slots=[CredentialSlot(name="chat_id", type="telegram", required=False, multi=True)],
        open_credential_slots=False,
        slot_bindings={"chat_id": ["c1", "c2"]},
        credential_pool=pool,
    )
    assert resolved == {"chat_id": ["111", "222"]}
    assert missing == []


def test_multi_slot_does_not_auto_bind():
    # Unlike single slots, a multi slot never auto-binds a unique-type credential.
    pool = _pool(PooledCredential(id="c1", name="ChatA", type="telegram", value="111"))
    resolved, missing = resolve_tool_credentials(
        declared_slots=[CredentialSlot(name="chat_id", type="telegram", required=False, multi=True)],
        open_credential_slots=False,
        slot_bindings={},
        credential_pool=pool,
    )
    assert resolved == {}
    assert missing == []


def test_open_slots_expose_only_bound_credentials():
    pool = _pool(
        PooledCredential(id="c1", name="Token", type="api_key", value="t"),
        PooledCredential(id="c2", name="Other", type="api_key", value="o"),
    )
    resolved, missing = resolve_tool_credentials(
        declared_slots=[],
        open_credential_slots=True,
        slot_bindings={"TOKEN": "c1"},
        credential_pool=pool,
    )
    assert resolved == {"TOKEN": "t"}
    assert missing == []
