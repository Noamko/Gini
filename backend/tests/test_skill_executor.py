"""Tests for skill prompt assembly."""
from types import SimpleNamespace

from app.services.skill_executor import build_skill_context, credential_env_var_name


def test_build_skill_context_advertises_handles_not_values():
    skill = SimpleNamespace(
        name="IMAP Reader",
        description="Read inbox contents",
        instructions="Use run_shell for IMAP access.",
        tools=[],
        credentials=[
            SimpleNamespace(name="IMAP Password", credential_type="password"),
        ],
    )

    context = build_skill_context(
        [skill],
        inject_credentials=True,
        decrypted_creds={"IMAP Password": "super-secret"},
    )

    assert "super-secret" not in context
    assert "IMAP Password" in context
    assert credential_env_var_name("IMAP Password") in context
