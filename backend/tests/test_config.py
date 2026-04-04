"""Tests for app.config — settings loading and defaults."""
from app.config import Settings


def test_settings_defaults():
    """Settings should have sensible defaults without any env file."""
    s = Settings(_env_file=None)
    assert s.app_name == "Gini"
    assert s.app_version == "0.1.0"
    assert s.debug is True
    assert s.default_llm_provider == "anthropic"
    assert s.default_temperature == 0.7
    assert s.default_max_tokens == 4096


def test_settings_override_from_env(monkeypatch):
    """Environment variables should override defaults."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
    monkeypatch.setenv("DEBUG", "false")
    s = Settings(_env_file=None)
    assert s.anthropic_api_key == "sk-test-key"
    assert s.debug is False
