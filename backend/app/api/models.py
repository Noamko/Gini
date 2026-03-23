"""Available LLM models endpoint — fetches from providers and caches in Redis."""
import json

import structlog
from fastapi import APIRouter

from app.config import settings
from app.dependencies import redis_client
from app.services.llm_gateway import llm_gateway

logger = structlog.get_logger("models_api")

router = APIRouter(tags=["models"])

CACHE_KEY = "gini:available_models"
CACHE_TTL = 3600  # 1 hour

# Well-known Anthropic models (Anthropic doesn't have a list-models API)
ANTHROPIC_MODELS = [
    {"id": "claude-opus-4-20250514", "name": "Claude Opus 4", "provider": "anthropic"},
    {"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet 4", "provider": "anthropic"},
    {"id": "claude-haiku-4-20250506", "name": "Claude Haiku 4", "provider": "anthropic"},
    {"id": "claude-3-5-sonnet-20241022", "name": "Claude 3.5 Sonnet", "provider": "anthropic"},
    {"id": "claude-3-5-haiku-20241022", "name": "Claude 3.5 Haiku", "provider": "anthropic"},
]


async def _fetch_openai_models() -> list[dict]:
    """Fetch chat-capable models from OpenAI API."""
    try:
        response = await llm_gateway.openai.models.list()
        models = []
        for m in response.data:
            # Filter to chat models only
            if any(prefix in m.id for prefix in ("gpt-4", "gpt-3.5", "o1", "o3", "o4")):
                if "realtime" in m.id or "audio" in m.id or "search" in m.id:
                    continue
                models.append({
                    "id": m.id,
                    "name": m.id,
                    "provider": "openai",
                })
        # Sort: newest/best first
        models.sort(key=lambda x: x["id"], reverse=True)
        return models
    except Exception as e:
        await logger.awarning("openai_models_fetch_failed", error=str(e))
        return []


@router.get("/api/models")
async def list_models(refresh: bool = False):
    """List available models from all configured providers. Cached for 1 hour."""
    if not refresh:
        cached = await redis_client.get(CACHE_KEY)
        if cached:
            return json.loads(cached)

    all_models = []

    # Anthropic (hardcoded — no list API)
    if settings.anthropic_api_key and not settings.anthropic_api_key.startswith("sk-your"):
        all_models.extend(ANTHROPIC_MODELS)

    # OpenAI (fetched from API)
    if settings.openai_api_key and not settings.openai_api_key.startswith("sk-your"):
        openai_models = await _fetch_openai_models()
        all_models.extend(openai_models)

    result = {"models": all_models}

    # Cache
    await redis_client.set(CACHE_KEY, json.dumps(result), ex=CACHE_TTL)

    return result
