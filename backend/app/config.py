from pathlib import Path

import yaml
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://gini:gini_dev_password@localhost:5432/gini"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # LLM API Keys
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # Credential Vault
    encryption_key: str = ""

    # Telegram
    telegram_bot_token: str = ""
    telegram_allowed_users: str = ""  # comma-separated Telegram user IDs

    # App settings (loaded from settings.yaml)
    app_name: str = "Gini"
    app_version: str = "0.1.0"
    debug: bool = True
    default_llm_provider: str = "anthropic"
    default_llm_model: str = "claude-sonnet-4-20250514"
    default_temperature: float = 0.7
    default_max_tokens: int = 4096

    model_config = {"env_file": ".env", "extra": "ignore"}


def load_settings() -> Settings:
    """Load settings from environment variables and settings.yaml."""
    settings = Settings()

    settings_path = Path("/app/settings.yaml")
    if settings_path.exists():
        with open(settings_path) as f:
            yaml_config = yaml.safe_load(f) or {}

        app_cfg = yaml_config.get("app", {})
        defaults_cfg = yaml_config.get("defaults", {})

        if app_cfg.get("name"):
            settings.app_name = app_cfg["name"]
        if app_cfg.get("version"):
            settings.app_version = app_cfg["version"]
        if "debug" in app_cfg:
            settings.debug = app_cfg["debug"]
        if defaults_cfg.get("llm_provider"):
            settings.default_llm_provider = defaults_cfg["llm_provider"]
        if defaults_cfg.get("llm_model"):
            settings.default_llm_model = defaults_cfg["llm_model"]
        if defaults_cfg.get("temperature") is not None:
            settings.default_temperature = defaults_cfg["temperature"]
        if defaults_cfg.get("max_tokens") is not None:
            settings.default_max_tokens = defaults_cfg["max_tokens"]

    return settings


settings = load_settings()
