"""Tests for skill (playbook) context injection and credential env-var naming."""

from types import SimpleNamespace

from app.services.skill_executor import build_skill_context, credential_env_var_name


def test_build_skill_context_is_instructions_only():
    skill = SimpleNamespace(
        name="Telegram",
        description="Send messages",
        instructions="Use send_telegram to notify the user.",
    )

    context = build_skill_context([skill])

    assert "## Assigned Skills (MANDATORY)" in context
    assert "send_telegram to notify" in context
    # Skills are playbooks now: tools and credentials are NOT advertised in the prompt.
    assert "Required tools" not in context
    assert "credential" not in context.lower()


def test_build_skill_context_empty():
    assert build_skill_context([]) == ""


def test_credential_env_var_name_normalizes():
    assert credential_env_var_name("Telegram Bot Token") == "GINI_CRED_TELEGRAM_BOT_TOKEN"
    assert credential_env_var_name("a---b") == "GINI_CRED_A_B"
