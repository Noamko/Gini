"""WebSocket chat endpoint with tool calling loop, sandbox execution, and HITL approval."""
import asyncio
import json
from decimal import Decimal
from uuid import UUID

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.dependencies import async_session
from app.event_bus.hitl import request_approval, resolve_approval, wait_for_approval
from app.models.agent import Agent
from app.models.conversation import Conversation
from app.models.message import Message
from app.observability.trace import TraceBuilder
from app.services.agent_orchestrator import (
    STATE_DELEGATING,
    STATE_THINKING,
    get_agent_by_name,
    run_sub_agent,
    set_agent_state,
)
from app.services.llm_gateway import LLMResponse, llm_gateway
from app.services.skill_executor import get_assembled_prompt, get_assembled_prompt_with_credentials
from app.services.tool_runner import execute_tool
from app.tools.registry import get_all_tool_specs, get_tool

logger = structlog.get_logger("chat")

router = APIRouter()

MAX_TOOL_ROUNDS = 100


async def _persist_message(conversation_id: UUID, **kwargs) -> None:
    """Fire-and-forget message persistence."""
    async with async_session() as db:
        msg = Message(conversation_id=conversation_id, **kwargs)
        db.add(msg)
        await db.commit()


async def _get_conversation_context(conversation_id: UUID) -> tuple[Conversation | None, Agent | None, list[dict]]:
    """Load conversation, its agent, and message history."""
    async with async_session() as db:
        conv = await db.get(Conversation, conversation_id)
        if not conv:
            return None, None, []

        agent = None
        if conv.agent_id:
            agent = await db.get(Agent, conv.agent_id)
        else:
            result = await db.execute(select(Agent).where(Agent.is_main == True))
            agent = result.scalar_one_or_none()

        result = await db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
        )
        db_messages = result.scalars().all()

        messages = []
        for m in db_messages:
            if m.role in ("user", "assistant"):
                messages.append({"role": m.role, "content": m.content or ""})

        return conv, agent, messages


@router.websocket("/ws/chat/{conversation_id}")
async def chat_websocket(websocket: WebSocket, conversation_id: UUID):
    await websocket.accept()
    await logger.ainfo("ws_connected", conversation_id=str(conversation_id))

    # Queue for incoming messages — allows the agent loop to run while we keep reading from WS
    incoming: asyncio.Queue = asyncio.Queue()

    async def ws_reader():
        """Read from WebSocket and put messages into the queue."""
        try:
            while True:
                raw = await websocket.receive_text()
                data = json.loads(raw)
                await incoming.put(data)
        except WebSocketDisconnect:
            await incoming.put(None)  # sentinel
        except Exception:
            await incoming.put(None)

    reader_task = asyncio.create_task(ws_reader())

    try:
        while True:
            data = await incoming.get()
            if data is None:
                break  # WS disconnected

            # Handle approval responses immediately
            if data.get("type") == "approval_response":
                approval_id = data.get("approval_id")
                approved = data.get("approved", False)
                reason = data.get("reason")
                await resolve_approval(approval_id, approved=approved, reason=reason)
                continue

            if data.get("type") != "user_message":
                continue

            user_content = data.get("content", "").strip()
            if not user_content:
                continue

            conv, agent, history = await _get_conversation_context(conversation_id)
            if not conv:
                await websocket.send_json({"type": "error", "message": "Conversation not found"})
                continue
            if not agent:
                await websocket.send_json({"type": "error", "message": "No agent configured"})
                continue

            # Persist user message in background
            asyncio.create_task(_persist_message(conversation_id=conversation_id, role="user", content=user_content))

            history.append({"role": "user", "content": user_content})

            tool_specs = await get_all_tool_specs()

            # Get assembled prompt (inject credentials for auto-approve agents)
            prompt_fn = get_assembled_prompt_with_credentials if agent.auto_approve else get_assembled_prompt
            system_prompt = await prompt_fn(agent)

            try:
                await _run_agent_loop(websocket, conversation_id, agent, history, tool_specs, incoming, system_prompt)
            except Exception as e:
                await logger.aerror("agent_loop_error", error=str(e))
                error_str = str(e)
                if "overloaded" in error_str.lower() or "529" in error_str:
                    user_msg = "The AI provider is temporarily overloaded. Please try again in a moment."
                elif "rate_limit" in error_str.lower() or "429" in error_str:
                    user_msg = "Rate limit reached. Please wait a moment and try again."
                elif "authentication" in error_str.lower() or "401" in error_str:
                    user_msg = "API key is invalid or expired. Check your settings."
                elif "credit balance" in error_str.lower() or "billing" in error_str.lower():
                    user_msg = "API credits exhausted. Please top up your account."
                else:
                    user_msg = error_str[:500]
                await websocket.send_json({"type": "error", "message": user_msg})

    except Exception as e:
        await logger.aerror("ws_error", error=str(e))
    finally:
        reader_task.cancel()
        await logger.ainfo("ws_disconnected", conversation_id=str(conversation_id))


async def _run_agent_loop(
    websocket: WebSocket,
    conversation_id: UUID,
    agent: Agent,
    messages: list[dict],
    tool_specs: list[dict],
    incoming: asyncio.Queue,
    system_prompt: str = "",
):
    """Run the agent loop: call LLM, execute tools if requested, repeat until text response.

    The incoming queue is used to process approval responses while waiting for HITL.
    """
    trace = TraceBuilder(
        conversation_id=str(conversation_id),
        agent_id=str(agent.id),
        agent_name=agent.name,
    )

    total_input_tokens = 0
    total_output_tokens = 0
    total_cost = 0.0

    for round_num in range(MAX_TOOL_ROUNDS):
        async with trace.step("llm_call", step_name=f"round_{round_num}", input_data={"message_count": len(messages)}) as step:
            response: LLMResponse = await llm_gateway.call_with_tools(
                messages=messages,
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
                "tool_calls": [{"name": tc["name"], "arguments": tc["arguments"]} for tc in response.tool_calls] if response.tool_calls else [],
            }

        total_input_tokens += response.input_tokens
        total_output_tokens += response.output_tokens
        total_cost += response.cost_usd

        # If no tool calls, we're done
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
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
                "cost_usd": total_cost,
                "duration_ms": response.duration_ms,
                "trace_id": trace.trace_id,
            })

            asyncio.create_task(_persist_message(
                conversation_id=conversation_id,
                role="assistant",
                content=response.content,
                model_used=response.model,
                token_count=total_input_tokens + total_output_tokens,
                cost_usd=Decimal(str(round(total_cost, 6))),
            ))
            return

        # Build assistant message with tool_use blocks
        assistant_content = []
        if response.content:
            assistant_content.append({"type": "text", "text": response.content})
            # Send thinking text (agent's reasoning before tool use)
            await websocket.send_json({
                "type": "assistant_thinking",
                "content": response.content,
            })
            await websocket.send_json({
                "type": "assistant_chunk",
                "content": response.content,
            })

        for tc in response.tool_calls:
            assistant_content.append({
                "type": "tool_use",
                "id": tc["id"],
                "name": tc["name"],
                "input": tc["arguments"],
            })

        messages.append({"role": "assistant", "content": assistant_content})

        # Execute each tool call
        tool_results_content = []
        for tc in response.tool_calls:
            tool_name = tc["name"]
            tool_args = tc["arguments"]
            tool_obj = get_tool(tool_name)

            needs_approval = (tool_obj.requires_approval if tool_obj else False) and not agent.auto_approve
            use_sandbox = tool_obj.requires_sandbox if tool_obj else False

            if needs_approval:
                # Send approval request to client
                pending = await request_approval(
                    tool_name=tool_name,
                    arguments=tool_args,
                    conversation_id=str(conversation_id),
                )

                await websocket.send_json({
                    "type": "approval_request",
                    "approval_id": pending.id,
                    "tool_name": tool_name,
                    "arguments": tool_args,
                    "tool_call_id": tc["id"],
                })

                # Drain the incoming queue for approval responses while waiting
                async def drain_approvals(pending=pending):
                    """Process approval responses from the queue while we wait."""
                    while not pending.event.is_set():
                        try:
                            data = await asyncio.wait_for(incoming.get(), timeout=1.0)
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

                # Wait for approval (with concurrent queue draining)
                drain_task = asyncio.create_task(drain_approvals())
                approved = await wait_for_approval(pending, timeout=300)
                drain_task.cancel()

                if not approved:
                    reject_reason = pending.reject_reason or "User rejected"
                    await websocket.send_json({
                        "type": "tool_call_result",
                        "tool_name": tool_name,
                        "tool_call_id": tc["id"],
                        "success": False,
                        "output": "",
                        "error": f"Rejected: {reject_reason}",
                        "duration_ms": 0,
                    })

                    tool_results_content.append({
                        "type": "tool_result",
                        "tool_use_id": tc["id"],
                        "content": f"Error: Tool execution was rejected by the user. Reason: {reject_reason}",
                    })
                    continue

            # Handle delegate_task specially via the orchestrator
            if tool_name == "delegate_task":
                agent_name = tool_args.get("agent_name", "")
                task_desc = tool_args.get("task", "")

                await websocket.send_json({
                    "type": "delegation_start",
                    "agent_name": agent_name,
                    "task": task_desc[:500],
                    "tool_call_id": tc["id"],
                })

                await set_agent_state(str(agent.id), STATE_DELEGATING, {"delegated_to": agent_name})

                sub_agent = await get_agent_by_name(agent_name)
                if not sub_agent:
                    await websocket.send_json({
                        "type": "delegation_complete",
                        "agent_name": agent_name,
                        "tool_call_id": tc["id"],
                        "success": False,
                        "content": f"Agent '{agent_name}' not found.",
                    })
                    tool_results_content.append({
                        "type": "tool_result",
                        "tool_use_id": tc["id"],
                        "content": f"Error: Agent '{agent_name}' not found. Available agents can be listed.",
                    })
                    await set_agent_state(str(agent.id), STATE_THINKING)
                    continue

                async with trace.step("delegation", step_name=f"delegate:{agent_name}", input_data={"task": task_desc[:500]}) as step:
                    delegation_result = await run_sub_agent(
                        agent=sub_agent,
                        task=task_desc,
                        parent_conversation_id=str(conversation_id),
                    )
                    step.cost_usd = delegation_result.get("cost_usd", 0)
                    step.input_tokens = delegation_result.get("input_tokens", 0)
                    step.output_tokens = delegation_result.get("output_tokens", 0)
                    step.model = delegation_result.get("model")
                    step.output_data = {"success": delegation_result["success"], "content_length": len(delegation_result.get("content", ""))}

                total_cost += delegation_result.get("cost_usd", 0)

                await websocket.send_json({
                    "type": "delegation_complete",
                    "agent_name": agent_name,
                    "tool_call_id": tc["id"],
                    "success": delegation_result["success"],
                    "content": delegation_result["content"][:2000],
                    "cost_usd": delegation_result.get("cost_usd", 0),
                    "duration_ms": delegation_result.get("duration_ms", 0),
                })

                await set_agent_state(str(agent.id), STATE_THINKING)

                tool_results_content.append({
                    "type": "tool_result",
                    "tool_use_id": tc["id"],
                    "content": delegation_result["content"][:10000],
                })
                continue

            # Notify client about tool call starting
            await websocket.send_json({
                "type": "tool_call_start",
                "tool_name": tool_name,
                "arguments": tool_args,
                "tool_call_id": tc["id"],
            })

            # Execute the tool (with sandbox if required, network for auto_approve agents)
            async with trace.step("tool_call", step_name=tool_name, input_data={"arguments": tool_args}) as step:
                result = await execute_tool(tool_name, tool_args, use_sandbox=use_sandbox, allow_network=agent.auto_approve)
                step.output_data = {"success": result.success, "output": result.output}
                if result.error:
                    step.error = result.error

            await websocket.send_json({
                "type": "tool_call_result",
                "tool_name": tool_name,
                "tool_call_id": tc["id"],
                "success": result.success,
                "output": result.output[:2000],
                "error": result.error,
                "duration_ms": result.metadata.get("duration_ms", 0),
                "sandboxed": result.metadata.get("sandboxed", False),
            })

            tool_output = result.output if result.success else f"Error: {result.error}"
            tool_results_content.append({
                "type": "tool_result",
                "tool_use_id": tc["id"],
                "content": tool_output[:10000],
            })

        messages.append({"role": "user", "content": tool_results_content})

    await websocket.send_json({
        "type": "error",
        "message": f"Agent exceeded maximum tool rounds ({MAX_TOOL_ROUNDS})",
    })
