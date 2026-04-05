"""WebSocket chat endpoint."""
import asyncio
import json
from uuid import UUID

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.dependencies import async_session
from app.event_bus.hitl import resolve_approval
from app.services import conversation_service
from app.services.chat_execution import run_chat_agent_loop
from app.services.execution_prep import prepare_chat_resources

logger = structlog.get_logger("chat")

router = APIRouter()


async def _persist_message(conversation_id: UUID, **kwargs) -> None:
    """Persist a message and touch the conversation timestamp."""
    async with async_session() as db:
        await conversation_service.create_message(db, conversation_id=conversation_id, **kwargs)


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

            async with async_session() as db:
                conv, agent, history = await conversation_service.get_conversation_agent_and_history(
                    db,
                    conversation_id,
                )
            if not conv:
                await websocket.send_json({"type": "error", "message": "Conversation not found"})
                continue
            if not agent:
                await websocket.send_json({"type": "error", "message": "No agent configured"})
                continue

            await _persist_message(conversation_id=conversation_id, role="user", content=user_content)

            history.append({"role": "user", "content": user_content})

            resources = await prepare_chat_resources(agent)

            try:
                await run_chat_agent_loop(
                    websocket=websocket,
                    conversation_id=conversation_id,
                    agent=agent,
                    messages=history,
                    tool_specs=resources.tool_specs,
                    tool_policy_by_name=resources.tool_policy_by_name,
                    incoming=incoming,
                    persist_message=_persist_message,
                    system_prompt=resources.system_prompt,
                )
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
