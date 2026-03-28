from decimal import Decimal

# Prices per 1M tokens (input, output) in USD
# Sources:
#   Anthropic: https://platform.claude.com/docs/en/docs/about-claude/models (verified 2026-03-28)
#   OpenAI: https://openai.com/api/pricing/ (verified 2026-03-28)

MODEL_PRICING: dict[str, tuple[Decimal, Decimal]] = {
    # Anthropic — Claude 4.6 (latest)
    "claude-opus-4-6": (Decimal("5.00"), Decimal("25.00")),
    "claude-sonnet-4-6": (Decimal("3.00"), Decimal("15.00")),
    # Anthropic — Claude 4.5
    "claude-opus-4-5": (Decimal("5.00"), Decimal("25.00")),
    "claude-sonnet-4-5": (Decimal("3.00"), Decimal("15.00")),
    "claude-haiku-4-5": (Decimal("1.00"), Decimal("5.00")),
    # Anthropic — Claude 4.1
    "claude-opus-4-1": (Decimal("15.00"), Decimal("75.00")),
    # Anthropic — Claude 4
    "claude-opus-4": (Decimal("15.00"), Decimal("75.00")),
    "claude-sonnet-4": (Decimal("3.00"), Decimal("15.00")),
    # Anthropic — Claude 3.5
    "claude-3-5-sonnet": (Decimal("3.00"), Decimal("15.00")),
    "claude-3-5-haiku": (Decimal("0.80"), Decimal("4.00")),
    # Anthropic — Claude 3 (deprecated)
    "claude-3-opus": (Decimal("15.00"), Decimal("75.00")),
    "claude-3-sonnet": (Decimal("3.00"), Decimal("15.00")),
    "claude-3-haiku": (Decimal("0.25"), Decimal("1.25")),
    # OpenAI — GPT-5.4
    "gpt-5.4": (Decimal("2.50"), Decimal("15.00")),
    "gpt-5.4-mini": (Decimal("0.75"), Decimal("4.50")),
    "gpt-5.4-nano": (Decimal("0.20"), Decimal("1.25")),
    # OpenAI — GPT-5.2
    "gpt-5.2-pro": (Decimal("30.00"), Decimal("120.00")),
    "gpt-5.2": (Decimal("10.00"), Decimal("40.00")),
    # OpenAI — GPT-5.1
    "gpt-5.1": (Decimal("10.00"), Decimal("40.00")),
    # OpenAI — GPT-5
    "gpt-5-pro": (Decimal("30.00"), Decimal("120.00")),
    "gpt-5": (Decimal("10.00"), Decimal("40.00")),
    "gpt-5-mini": (Decimal("1.50"), Decimal("6.00")),
    "gpt-5-nano": (Decimal("0.50"), Decimal("2.00")),
    # OpenAI — GPT-4o
    "gpt-4o": (Decimal("2.50"), Decimal("10.00")),
    "gpt-4o-mini": (Decimal("0.15"), Decimal("0.60")),
    # OpenAI — GPT-4.1
    "gpt-4.1": (Decimal("2.00"), Decimal("8.00")),
    "gpt-4.1-mini": (Decimal("0.40"), Decimal("1.60")),
    "gpt-4.1-nano": (Decimal("0.10"), Decimal("0.40")),
    # OpenAI — GPT-4 Turbo / GPT-4
    "gpt-4-turbo": (Decimal("10.00"), Decimal("30.00")),
    "gpt-4": (Decimal("30.00"), Decimal("60.00")),
    # OpenAI — GPT-3.5
    "gpt-3.5-turbo": (Decimal("0.50"), Decimal("1.50")),
    # OpenAI — o-series reasoning
    "o1-pro": (Decimal("150.00"), Decimal("600.00")),
    "o1": (Decimal("15.00"), Decimal("60.00")),
    "o1-mini": (Decimal("3.00"), Decimal("12.00")),
    "o3": (Decimal("10.00"), Decimal("40.00")),
    "o3-mini": (Decimal("1.10"), Decimal("4.40")),
    "o4-mini": (Decimal("1.10"), Decimal("4.40")),
}


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    pricing = MODEL_PRICING.get(model)
    if not pricing:
        # Try prefix match for dated variants (e.g. gpt-5.4-2026-03-05 → gpt-5.4)
        for key, val in MODEL_PRICING.items():
            if model.startswith(key):
                pricing = val
                break
    if not pricing:
        return Decimal("0")
    input_price, output_price = pricing
    cost = (input_price * input_tokens + output_price * output_tokens) / Decimal("1000000")
    return cost.quantize(Decimal("0.000001"))
