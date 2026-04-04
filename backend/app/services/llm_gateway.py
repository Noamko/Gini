"""Unified LLM gateway supporting OpenAI and Anthropic with streaming and tool use."""
import asyncio
import json
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field

import structlog
from anthropic import APIStatusError as AnthropicAPIStatusError
from anthropic import AsyncAnthropic
from openai import APIStatusError as OpenAIAPIStatusError
from openai import AsyncOpenAI

from app.config import settings
from app.services.cost_tracker import calculate_cost

logger = structlog.get_logger("llm_gateway")

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 529}
MAX_RETRIES = 3
BASE_DELAY = 1.0  # seconds


@dataclass
class LLMResponse:
    content: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    cost_usd: float = 0.0
    duration_ms: float = 0.0
    tool_calls: list[dict] = field(default_factory=list)
    stop_reason: str = ""


@dataclass
class StreamChunk:
    delta: str = ""
    is_final: bool = False
    response: LLMResponse | None = None


class LLMGateway:
    def __init__(self):
        self._anthropic: AsyncAnthropic | None = None
        self._openai: AsyncOpenAI | None = None

    @property
    def anthropic(self) -> AsyncAnthropic:
        if not self._anthropic:
            self._anthropic = AsyncAnthropic(
                api_key=settings.anthropic_api_key,
                timeout=120.0,
            )
        return self._anthropic

    @property
    def openai(self) -> AsyncOpenAI:
        if not self._openai:
            self._openai = AsyncOpenAI(
                api_key=settings.openai_api_key,
                timeout=120.0,
            )
        return self._openai

    async def call_with_tools(
        self,
        messages: list[dict],
        system_prompt: str = "",
        tools: list[dict] | None = None,
        provider: str = "anthropic",
        model: str = "claude-sonnet-4-20250514",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Non-streaming call that supports tool use. Returns the full response."""
        start = time.perf_counter()

        if provider == "anthropic":
            return await self._call_anthropic(messages, system_prompt, tools, model, temperature, max_tokens, start)
        elif provider == "openai":
            return await self._call_openai(messages, system_prompt, tools, model, temperature, max_tokens, start)
        else:
            raise ValueError(f"Unsupported provider: {provider}")

    async def _call_anthropic(
        self, messages, system_prompt, tools, model, temperature, max_tokens, start
    ) -> LLMResponse:
        kwargs = {
            "model": model,
            "messages": messages,
            "system": system_prompt or "You are a helpful assistant.",
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = tools

        last_error = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = await self.anthropic.messages.create(**kwargs)
                break
            except AnthropicAPIStatusError as e:
                if e.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES:
                    delay = BASE_DELAY * (2 ** attempt)
                    await logger.awarning("llm_retry", provider="anthropic", attempt=attempt + 1, status=e.status_code, delay=delay)
                    last_error = e
                    await asyncio.sleep(delay)
                else:
                    raise
        else:
            raise last_error  # type: ignore[misc]

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        cost = calculate_cost(model, response.usage.input_tokens, response.usage.output_tokens)

        # Extract text and tool calls from content blocks
        text_parts = []
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "name": block.name,
                    "arguments": block.input,
                })

        await logger.ainfo(
            "llm_response",
            provider="anthropic",
            model=model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cost_usd=float(cost),
            duration_ms=duration_ms,
            stop_reason=response.stop_reason,
            tool_calls=len(tool_calls),
        )

        return LLMResponse(
            content="\n".join(text_parts),
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=model,
            cost_usd=float(cost),
            duration_ms=duration_ms,
            tool_calls=tool_calls,
            stop_reason=response.stop_reason,
        )

    def _convert_messages_for_openai(self, messages: list[dict]) -> list[dict]:
        """Convert Anthropic-style tool_use/tool_result messages to OpenAI format."""
        converted = []
        for msg in messages:
            if msg["role"] == "assistant" and isinstance(msg.get("content"), list):
                # Anthropic format: content is a list of blocks (text, tool_use)
                text_parts = []
                tool_calls = []
                for block in msg["content"]:
                    if block.get("type") == "text":
                        text_parts.append(block["text"])
                    elif block.get("type") == "tool_use":
                        tool_calls.append({
                            "id": block["id"],
                            "type": "function",
                            "function": {
                                "name": block["name"],
                                "arguments": json.dumps(block.get("input", {})),
                            },
                        })
                openai_msg = {"role": "assistant", "content": "\n".join(text_parts) if text_parts else None}
                if tool_calls:
                    openai_msg["tool_calls"] = tool_calls
                converted.append(openai_msg)
            elif msg["role"] == "user" and isinstance(msg.get("content"), list):
                # Anthropic format: tool_result blocks
                for block in msg["content"]:
                    if block.get("type") == "tool_result":
                        converted.append({
                            "role": "tool",
                            "tool_call_id": block["tool_use_id"],
                            "content": block.get("content", ""),
                        })
                    else:
                        converted.append(msg)
                        break
            else:
                converted.append(msg)
        return converted

    async def _call_openai(
        self, messages, system_prompt, tools, model, temperature, max_tokens, start
    ) -> LLMResponse:
        openai_messages = []
        if system_prompt:
            openai_messages.append({"role": "system", "content": system_prompt})
        openai_messages.extend(self._convert_messages_for_openai(messages))

        # Newer OpenAI models (gpt-5.x, o1, o3, o4, gpt-4.1) use max_completion_tokens
        uses_new_param = any(model.startswith(p) for p in ("gpt-5", "gpt-4.1", "o1", "o3", "o4"))
        token_param = "max_completion_tokens" if uses_new_param else "max_tokens"

        kwargs = {
            "model": model,
            "messages": openai_messages,
            "temperature": temperature,
            token_param: max_tokens,
        }
        if tools:
            kwargs["tools"] = [
                {"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}}
                for t in tools
            ]

        last_error = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = await self.openai.chat.completions.create(**kwargs)
                break
            except OpenAIAPIStatusError as e:
                if e.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES:
                    delay = BASE_DELAY * (2 ** attempt)
                    await logger.awarning("llm_retry", provider="openai", attempt=attempt + 1, status=e.status_code, delay=delay)
                    last_error = e
                    await asyncio.sleep(delay)
                else:
                    raise
        else:
            raise last_error  # type: ignore[misc]

        choice = response.choices[0]

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        input_tokens = response.usage.prompt_tokens if response.usage else 0
        output_tokens = response.usage.completion_tokens if response.usage else 0
        cost = calculate_cost(model, input_tokens, output_tokens)

        tool_calls = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments),
                })

        await logger.ainfo(
            "llm_response",
            provider="openai",
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=float(cost),
            duration_ms=duration_ms,
            stop_reason=choice.finish_reason,
            tool_calls=len(tool_calls),
        )

        return LLMResponse(
            content=choice.message.content or "",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=model,
            cost_usd=float(cost),
            duration_ms=duration_ms,
            tool_calls=tool_calls,
            stop_reason=choice.finish_reason or "",
        )

    async def stream_chat(
        self,
        messages: list[dict],
        system_prompt: str = "",
        provider: str = "anthropic",
        model: str = "claude-sonnet-4-20250514",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream a simple text response (no tools)."""
        start = time.perf_counter()

        if provider == "anthropic":
            async for chunk in self._stream_anthropic(messages, system_prompt, model, temperature, max_tokens, start):
                yield chunk
        elif provider == "openai":
            async for chunk in self._stream_openai(messages, system_prompt, model, temperature, max_tokens, start):
                yield chunk
        else:
            raise ValueError(f"Unsupported provider: {provider}")

    async def _stream_anthropic(
        self, messages, system_prompt, model, temperature, max_tokens, start
    ) -> AsyncGenerator[StreamChunk, None]:
        full_content = ""
        input_tokens = 0
        output_tokens = 0

        async with self.anthropic.messages.stream(
            model=model,
            messages=messages,
            system=system_prompt or "You are a helpful assistant.",
            temperature=temperature,
            max_tokens=max_tokens,
        ) as stream:
            async for text in stream.text_stream:
                full_content += text
                yield StreamChunk(delta=text)

            response = await stream.get_final_message()
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        cost = calculate_cost(model, input_tokens, output_tokens)

        await logger.ainfo("llm_response", provider="anthropic", model=model,
                           input_tokens=input_tokens, output_tokens=output_tokens,
                           cost_usd=float(cost), duration_ms=duration_ms)

        yield StreamChunk(
            is_final=True,
            response=LLMResponse(content=full_content, input_tokens=input_tokens,
                                 output_tokens=output_tokens, model=model,
                                 cost_usd=float(cost), duration_ms=duration_ms),
        )

    async def _stream_openai(
        self, messages, system_prompt, model, temperature, max_tokens, start
    ) -> AsyncGenerator[StreamChunk, None]:
        full_content = ""
        openai_messages = []
        if system_prompt:
            openai_messages.append({"role": "system", "content": system_prompt})
        openai_messages.extend(messages)

        uses_new_param = any(model.startswith(p) for p in ("gpt-5", "gpt-4.1", "o1", "o3", "o4"))
        token_kwarg = {"max_completion_tokens": max_tokens} if uses_new_param else {"max_tokens": max_tokens}

        stream = await self.openai.chat.completions.create(
            model=model, messages=openai_messages, temperature=temperature,
            **token_kwarg, stream=True, stream_options={"include_usage": True},
        )

        input_tokens = 0
        output_tokens = 0

        async for chunk in stream:
            if chunk.usage:
                input_tokens = chunk.usage.prompt_tokens
                output_tokens = chunk.usage.completion_tokens
            if chunk.choices and chunk.choices[0].delta.content:
                delta = chunk.choices[0].delta.content
                full_content += delta
                yield StreamChunk(delta=delta)

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        cost = calculate_cost(model, input_tokens, output_tokens)

        await logger.ainfo("llm_response", provider="openai", model=model,
                           input_tokens=input_tokens, output_tokens=output_tokens,
                           cost_usd=float(cost), duration_ms=duration_ms)

        yield StreamChunk(
            is_final=True,
            response=LLMResponse(content=full_content, input_tokens=input_tokens,
                                 output_tokens=output_tokens, model=model,
                                 cost_usd=float(cost), duration_ms=duration_ms),
        )


# Singleton
llm_gateway = LLMGateway()
