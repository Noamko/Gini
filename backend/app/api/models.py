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

async def _fetch_anthropic_models() -> list[dict]:
    """Fetch available models from Anthropic API."""
    try:
        client = llm_gateway.anthropic
        models = await client.models.list()
        return [
            {"id": m.id, "name": m.display_name, "provider": "anthropic"}
            for m in models.data
        ]
    except Exception as e:
        await logger.awarning("anthropic_models_fetch_failed", error=str(e))
        return []


OPENAI_CHAT_PREFIXES = ("gpt-3.5", "gpt-4", "gpt-5", "o1", "o3", "o4")
OPENAI_EXCLUDE = ("realtime", "audio", "tts", "transcribe", "search", "instruct", "codex", "chat-latest", "16k", "image")


async def _fetch_openai_models() -> list[dict]:
    """Fetch chat-capable models from OpenAI API."""
    try:
        response = await llm_gateway.openai.models.list()
        models = []
        for m in response.data:
            if not any(m.id.startswith(p) for p in OPENAI_CHAT_PREFIXES):
                continue
            if any(ex in m.id for ex in OPENAI_EXCLUDE):
                continue
            models.append({
                "id": m.id,
                "name": m.id,
                "provider": "openai",
            })
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

    # Anthropic (fetched from API)
    if settings.anthropic_api_key and not settings.anthropic_api_key.startswith("sk-your"):
        anthropic_models = await _fetch_anthropic_models()
        all_models.extend(anthropic_models)

    # OpenAI (fetched from API)
    if settings.openai_api_key and not settings.openai_api_key.startswith("sk-your"):
        openai_models = await _fetch_openai_models()
        all_models.extend(openai_models)

    result = {"models": all_models}

    # Cache
    await redis_client.set(CACHE_KEY, json.dumps(result), ex=CACHE_TTL)

    return result
