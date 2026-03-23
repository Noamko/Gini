from decimal import Decimal

# Prices per 1M tokens (input, output) in USD
MODEL_PRICING: dict[str, tuple[Decimal, Decimal]] = {
    # Anthropic
    "claude-sonnet-4-20250514": (Decimal("3.00"), Decimal("15.00")),
    "claude-opus-4-20250514": (Decimal("15.00"), Decimal("75.00")),
    "claude-haiku-3-5-20241022": (Decimal("0.80"), Decimal("4.00")),
    # OpenAI
    "gpt-4o": (Decimal("2.50"), Decimal("10.00")),
    "gpt-4o-mini": (Decimal("0.15"), Decimal("0.60")),
    "gpt-4-turbo": (Decimal("10.00"), Decimal("30.00")),
}


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    pricing = MODEL_PRICING.get(model)
    if not pricing:
        return Decimal("0")
    input_price, output_price = pricing
    cost = (input_price * input_tokens + output_price * output_tokens) / Decimal("1000000")
    return cost.quantize(Decimal("0.000001"))
