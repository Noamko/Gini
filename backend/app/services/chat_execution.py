"""Interactive chat execution helpers."""
import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from decimal import Decimal
from uuid import UUID

from fastapi import WebSocket

from app.event_bus.hitl import request_approval, resolve_approval, wait_for_approval
from app.models.agent import Agent
from app.observability.trace import TraceBuilder
from app.services.agent_orchestrator import (
    STATE_DELEGATING,
    STATE_THINKING,
    get_agent_by_name,
    run_sub_agent,
    set_agent_state,
)
from app.services.autonomous_execution import (
    AutonomousContext,
    ToolExecutionResult,
    process_tool_response,
)
from app.services.llm_gateway import LLMResponse, llm_gateway
from app.services.tool_catalog import ToolPolicy
from app.services.tool_runner import execute_tool

MAX_TOOL_ROUNDS = 100

PersistMessageHook = Callable[..., Awaitable[None]]


class InteractiveToolExecutor:
    """Chat-specific adapter around the shared tool-processing primitives."""

    def __init__(
        self,
        *,
        websocket: WebSocket,
        conversation_id: UUID,
        agent: Agent,
        incoming: asyncio.Queue,
        trace: TraceBuilder,
        persist_message: PersistMessageHook,
    ) -> None:
        self.websocket = websocket
        self.conversation_id = conversation_id
        self.agent = agent
        self.incoming = incoming
        self.trace = trace
        self.persist_message = persist_message

    async def persist_tool_round(self, content: str | None, assistant_content: list[dict]) -> None:
        await self.persist_message(
            conversation_id=self.conversation_id,
            role="assistant",
            content=content or "",
            tool_calls=[
                block
                for block in assistant_content
                if block.get("type") == "tool_use"
            ],
            metadata={"hidden_from_ui": True, "message_kind": "tool_round"},
        )

    async def persist_tool_result(
        self,
        tool_name: str,
        tc: dict,
        tool_output: str,
        _success: bool,
        _error: str | None,
    ) -> None:
        await self.persist_message(
            conversation_id=self.conversation_id,
            role="tool",
            content=tool_output[:10000],
            tool_call_id=tc["id"],
            metadata={"hidden_from_ui": True, "tool_name": tool_name},
        )

    async def handle_tool_call(self, tc: dict, tool_policy: ToolPolicy | None) -> ToolExecutionResult:
        tool_name = tc["name"]
        tool_args = tc["arguments"]

        needs_approval = (tool_policy.requires_approval if tool_policy else False) and not self.agent.auto_approve
        use_sandbox = tool_policy.requires_sandbox if tool_policy else False

        if needs_approval:
            approval_result = await self._request_tool_approval(tc)
            if approval_result:
                return approval_result

        if tool_name == "delegate_task":
            return await self._run_delegation(tc)

        return await self._execute_standard_tool(tc, use_sandbox=use_sandbox)

    async def _request_tool_approval(self, tc: dict) -> ToolExecutionResult | None:
        tool_name = tc["name"]
        tool_args = tc["arguments"]
        pending = await request_approval(
            tool_name=tool_name,
            arguments=tool_args,
            conversation_id=str(self.conversation_id),
        )

        await self.websocket.send_json({
            "type": "approval_request",
            "approval_id": pending.id,
            "tool_name": tool_name,
            "arguments": tool_args,
            "tool_call_id": tc["id"],
        })

        async def drain_approvals() -> None:
            while not pending.event.is_set():
                try:
                    data = await asyncio.wait_for(self.incoming.get(), timeout=1.0)
                    if data is None:
                        return
                    if data.get("type") == "approval_response":
                        await resolve_approval(
                            data["approval_id"],
                            approved=data.get("approved", False),
                            reason=data.get("reason"),
                        )
                except TimeoutError:
                    continue

        drain_task = asyncio.create_task(drain_approvals())
        try:
            approved = await wait_for_approval(pending, timeout=300)
        finally:
            drain_task.cancel()
            with suppress(asyncio.CancelledError):
                await drain_task

        if approved:
            return None

        reject_reason = pending.reject_reason or "User rejected"
        await self.websocket.send_json({
            "type": "tool_call_result",
            "tool_name": tool_name,
            "tool_call_id": tc["id"],
            "success": False,
            "output": "",
            "error": f"Rejected: {reject_reason}",
            "duration_ms": 0,
        })
        return ToolExecutionResult(
            output=f"Error: Tool execution was rejected by the user. Reason: {reject_reason}",
            success=False,
            error=f"Rejected: {reject_reason}",
        )

    async def _run_delegation(self, tc: dict) -> ToolExecutionResult:
        tool_args = tc["arguments"]
        agent_name = tool_args.get("agent_name", "")
        task_desc = tool_args.get("task", "")

        await self.websocket.send_json({
            "type": "delegation_start",
            "agent_name": agent_name,
            "task": task_desc[:500],
            "tool_call_id": tc["id"],
        })

        await set_agent_state(str(self.agent.id), STATE_DELEGATING, {"delegated_to": agent_name})

        sub_agent = await get_agent_by_name(agent_name)
        if not sub_agent:
            await self.websocket.send_json({
                "type": "delegation_complete",
                "agent_name": agent_name,
                "tool_call_id": tc["id"],
                "success": False,
                "content": f"Agent '{agent_name}' not found.",
            })
            await set_agent_state(str(self.agent.id), STATE_THINKING)
            return ToolExecutionResult(
                output=f"Error: Agent '{agent_name}' not found. Available agents can be listed.",
                success=False,
                error=f"Agent '{agent_name}' not found.",
            )

        async with self.trace.step("delegation", step_name=f"delegate:{agent_name}", input_data={"task": task_desc[:500]}) as step:
            delegation_result = await run_sub_agent(
                agent=sub_agent,
                task=task_desc,
                parent_conversation_id=str(self.conversation_id),
            )
            step.cost_usd = delegation_result.get("cost_usd", 0)
            step.input_tokens = delegation_result.get("input_tokens", 0)
            step.output_tokens = delegation_result.get("output_tokens", 0)
            step.model = delegation_result.get("model")
            step.output_data = {
                "success": delegation_result["success"],
                "content_length": len(delegation_result.get("content", "")),
            }

        await self.websocket.send_json({
            "type": "delegation_complete",
            "agent_name": agent_name,
            "tool_call_id": tc["id"],
            "success": delegation_result["success"],
            "content": delegation_result["content"][:2000],
            "cost_usd": delegation_result.get("cost_usd", 0),
            "duration_ms": delegation_result.get("duration_ms", 0),
        })

        await set_agent_state(str(self.agent.id), STATE_THINKING)
        return ToolExecutionResult(
            output=delegation_result["content"][:10000],
            success=delegation_result["success"],
            error=None if delegation_result["success"] else delegation_result["content"][:10000],
            extra_cost_usd=delegation_result.get("cost_usd", 0.0),
        )

    async def _execute_standard_tool(self, tc: dict, *, use_sandbox: bool) -> ToolExecutionResult:
        tool_name = tc["name"]
        tool_args = tc["arguments"]

        await self.websocket.send_json({
            "type": "tool_call_start",
            "tool_name": tool_name,
            "arguments": tool_args,
            "tool_call_id": tc["id"],
        })

        async with self.trace.step("tool_call", step_name=tool_name, input_data={"arguments": tool_args}) as step:
            result = await execute_tool(
                tool_name,
                tool_args,
                use_sandbox=use_sandbox,
                allow_network=self.agent.auto_approve,
            )
            step.output_data = {"success": result.success, "output": result.output}
            if result.error:
                step.error = result.error

        await self.websocket.send_json({
            "type": "tool_call_result",
            "tool_name": tool_name,
            "tool_call_id": tc["id"],
            "success": result.success,
            "output": result.output[:2000],
            "error": result.error,
            "duration_ms": result.metadata.get("duration_ms", 0),
            "sandboxed": result.metadata.get("sandboxed", False),
        })
        return ToolExecutionResult(
            output=result.output if result.success else f"Error: {result.error}",
            success=result.success,
            error=result.error,
        )


async def run_chat_agent_loop(
    *,
    websocket: WebSocket,
    conversation_id: UUID,
    agent: Agent,
    messages: list[dict],
    tool_specs: list[dict],
    tool_policy_by_name: dict[str, ToolPolicy],
    incoming: asyncio.Queue,
    persist_message: PersistMessageHook,
    system_prompt: str = "",
    max_tool_rounds: int = MAX_TOOL_ROUNDS,
) -> None:
    """Run the interactive chat agent loop until it emits a final assistant message."""
    trace = TraceBuilder(
        conversation_id=str(conversation_id),
        agent_id=str(agent.id),
        agent_name=agent.name,
    )
    context = AutonomousContext(messages=messages)
    tool_executor = InteractiveToolExecutor(
        websocket=websocket,
        conversation_id=conversation_id,
        agent=agent,
        incoming=incoming,
        trace=trace,
        persist_message=persist_message,
    )

    for round_num in range(max_tool_rounds):
        async with trace.step("llm_call", step_name=f"round_{round_num}", input_data={"message_count": len(context.messages)}) as step:
            response: LLMResponse = await llm_gateway.call_with_tools(
                messages=context.messages,
                system_prompt=system_prompt or agent.system_prompt,
                tools=tool_specs if tool_specs else None,
                provider=agent.llm_provider,
                model=agent.llm_model,
                temperature=agent.temperature,
                max_tokens=agent.max_tokens,
            )
            step.model = response.model
            step.input_tokens = response.input_tokens
            step.output_tokens = response.output_tokens
            step.cost_usd = response.cost_usd
            step.output_data = {
                "content": response.content or "",
                "tool_calls": [
                    {"name": tc["name"], "arguments": tc["arguments"]}
                    for tc in response.tool_calls
                ] if response.tool_calls else [],
            }

        context.total_input_tokens += response.input_tokens
        context.total_output_tokens += response.output_tokens
        context.total_cost_usd += response.cost_usd
        context.steps.append({
            "type": "llm_call",
            "round": round_num,
            "content": (response.content or "")[:1000],
            "tool_calls": len(response.tool_calls) if response.tool_calls else 0,
            "tokens": response.input_tokens + response.output_tokens,
        })

        if not response.tool_calls:
            if response.content:
                await websocket.send_json({
                    "type": "assistant_chunk",
                    "content": response.content,
                })

            await websocket.send_json({
                "type": "assistant_message_complete",
                "content": response.content,
                "model": response.model,
                "input_tokens": context.total_input_tokens,
                "output_tokens": context.total_output_tokens,
                "cost_usd": context.total_cost_usd,
                "duration_ms": response.duration_ms,
                "trace_id": trace.trace_id,
            })

            await persist_message(
                conversation_id=conversation_id,
                role="assistant",
                content=response.content,
                model_used=response.model,
                token_count=context.total_input_tokens + context.total_output_tokens,
                cost_usd=Decimal(str(round(context.total_cost_usd, 6))),
            )
            return

        if response.content:
            await websocket.send_json({
                "type": "assistant_thinking",
                "content": response.content,
            })
            await websocket.send_json({
                "type": "assistant_chunk",
                "content": response.content,
            })

        await process_tool_response(
            response=response,
            context=context,
            tool_policy_by_name=tool_policy_by_name,
            tool_handler=tool_executor.handle_tool_call,
            on_tool_round_persist=tool_executor.persist_tool_round,
            on_tool_result=tool_executor.persist_tool_result,
        )

    await websocket.send_json({
        "type": "error",
        "message": f"Agent exceeded maximum tool rounds ({max_tool_rounds})",
    })
