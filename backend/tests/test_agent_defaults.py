"""AgentCreate provider/model defaulting — no provider/model mismatch."""

from app.config import default_model_for_provider
from app.schemas.agent import AgentCreate, AgentUpdate


def test_defaults_to_openai():
    a = AgentCreate(name="x", system_prompt="y")
    assert a.llm_provider == "openai"
    assert a.llm_model == "gpt-5.5"


def test_openai_provider_without_model_fills_openai_default():
    a = AgentCreate(name="x", system_prompt="y", llm_provider="openai")
    assert a.llm_model == "gpt-5.5"


def test_anthropic_provider_without_model_fills_claude_default():
    a = AgentCreate(name="x", system_prompt="y", llm_provider="anthropic")
    assert a.llm_model == default_model_for_provider("anthropic")
    assert a.llm_model.startswith("claude")


def test_explicit_model_is_respected():
    a = AgentCreate(name="x", system_prompt="y", llm_provider="openai", llm_model="gpt-5.4")
    assert a.llm_model == "gpt-5.4"


def test_update_changing_provider_without_model_snaps_model():
    u = AgentUpdate(llm_provider="anthropic")
    assert u.llm_model == default_model_for_provider("anthropic")
