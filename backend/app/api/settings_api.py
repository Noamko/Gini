"""Runtime settings API — read/update app configuration."""
from pydantic import BaseModel
from fastapi import APIRouter

from app.config import settings
from app.dependencies import redis_client
from app.services.cost_tracker import MODEL_PRICING

router = APIRouter(tags=["settings"])

SETTINGS_REDIS_KEY = "gini:settings"


class AppSettings(BaseModel):
    app_name: str
    app_version: str
    debug: bool
    default_llm_provider: str
    default_llm_model: str
    default_temperature: float
    default_max_tokens: int
    has_openai_key: bool
    has_anthropic_key: bool


class SettingsUpdate(BaseModel):
    default_llm_provider: str | None = None
    default_llm_model: str | None = None
    default_temperature: float | None = None
    default_max_tokens: int | None = None


@router.get("/api/settings")
async def get_settings() -> AppSettings:
    return AppSettings(
        app_name=settings.app_name,
        app_version=settings.app_version,
        debug=settings.debug,
        default_llm_provider=settings.default_llm_provider,
        default_llm_model=settings.default_llm_model,
        default_temperature=settings.default_temperature,
        default_max_tokens=settings.default_max_tokens,
        has_openai_key=bool(settings.openai_api_key and not settings.openai_api_key.startswith("sk-your")),
        has_anthropic_key=bool(settings.anthropic_api_key and not settings.anthropic_api_key.startswith("sk-your")),
    )


@router.put("/api/settings")
async def update_settings(body: SettingsUpdate) -> AppSettings:
    if body.default_llm_provider is not None:
        settings.default_llm_provider = body.default_llm_provider
    if body.default_llm_model is not None:
        settings.default_llm_model = body.default_llm_model
    if body.default_temperature is not None:
        settings.default_temperature = body.default_temperature
    if body.default_max_tokens is not None:
        settings.default_max_tokens = body.default_max_tokens

    return await get_settings()


@router.get("/api/pricing")
async def get_pricing():
    """Return model pricing table."""
    models = []
    for model_id, (input_price, output_price) in MODEL_PRICING.items():
        provider = "anthropic" if model_id.startswith("claude") else "openai"
        models.append({
            "id": model_id,
            "provider": provider,
            "input_per_1m": float(input_price),
            "output_per_1m": float(output_price),
        })
    models.sort(key=lambda m: (m["provider"], -m["input_per_1m"]))
    return {"models": models}
