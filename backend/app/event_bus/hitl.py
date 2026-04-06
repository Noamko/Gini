"""Human-in-the-Loop approval flow.

Manages pending approvals using asyncio.Event for signaling.
The chat WebSocket handler sends approval requests and listens for responses.
"""
import asyncio
import json
import uuid
from dataclasses import dataclass

import structlog

from app.event_bus.bus import event_bus
from app.event_bus.events import EventTypes
from app.dependencies import redis_client

logger = structlog.get_logger("hitl")

APPROVAL_TIMEOUT = 300  # 5 minutes
APPROVAL_KEY_PREFIX = "gini:approval:"


@dataclass
class PendingApproval:
    id: str
    event_id: str
    tool_name: str
    arguments: dict
    conversation_id: str | None
    run_id: str | None
    agent_id: str | None
    source: str
    event: asyncio.Event
    approved: bool | None = None
    reject_reason: str | None = None


# In-memory store of pending approvals keyed by approval_id
_pending: dict[str, PendingApproval] = {}


async def request_approval(
    tool_name: str,
    arguments: dict,
    conversation_id: str | None = None,
    run_id: str | None = None,
    agent_id: str | None = None,
    source: str = "hitl",
) -> PendingApproval:
    """Create an approval request and return a PendingApproval that can be awaited."""
    approval_id = str(uuid.uuid4())

    pending = PendingApproval(
        id=approval_id,
        event_id="",
        tool_name=tool_name,
        arguments=arguments,
        conversation_id=conversation_id,
        run_id=run_id,
        agent_id=agent_id,
        source=source,
        event=asyncio.Event(),
    )
    _pending[approval_id] = pending

    # Persist the event
    event_id = await event_bus.publish(
        event_type=EventTypes.APPROVAL_REQUESTED,
        payload={"tool_name": tool_name, "arguments": arguments},
        correlation_id=approval_id,
        conversation_id=conversation_id,
        source=source,
    )
    pending.event_id = event_id
    await redis_client.setex(
        f"{APPROVAL_KEY_PREFIX}{approval_id}",
        APPROVAL_TIMEOUT,
        json.dumps({
            "id": approval_id,
            "event_id": event_id,
            "tool_name": tool_name,
            "arguments": arguments,
            "conversation_id": conversation_id,
            "run_id": run_id,
            "agent_id": agent_id,
            "source": source,
            "status": "pending",
            "reason": None,
        }),
    )

    await logger.ainfo("approval_requested", approval_id=approval_id, tool=tool_name)
    return pending


async def wait_for_approval(pending: PendingApproval, timeout: float = APPROVAL_TIMEOUT) -> bool:
    """Wait for user to approve or reject. Returns True if approved."""
    deadline = asyncio.get_running_loop().time() + timeout
    try:
        while True:
            raw = await redis_client.get(f"{APPROVAL_KEY_PREFIX}{pending.id}")
            if raw:
                state = json.loads(raw)
                status = state.get("status")
                if status == "approved":
                    pending.approved = True
                    pending.reject_reason = None
                    break
                if status == "rejected":
                    pending.approved = False
                    pending.reject_reason = state.get("reason")
                    break

            if pending.event.is_set():
                break

            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError

            await asyncio.sleep(0.5)
    except TimeoutError:
        await logger.awarning("approval_timeout", approval_id=pending.id)
        pending.approved = False
        pending.reject_reason = "Approval timed out"
        await redis_client.setex(
            f"{APPROVAL_KEY_PREFIX}{pending.id}",
            APPROVAL_TIMEOUT,
            json.dumps({
                "id": pending.id,
                "event_id": pending.event_id,
                "tool_name": pending.tool_name,
                "arguments": pending.arguments,
                "conversation_id": pending.conversation_id,
                "run_id": pending.run_id,
                "agent_id": pending.agent_id,
                "source": pending.source,
                "status": "timeout",
                "reason": pending.reject_reason,
            }),
        )
        await event_bus.update_event_status(pending.event_id, "timeout")
    finally:
        _pending.pop(pending.id, None)

    return pending.approved is True


async def resolve_approval(approval_id: str, approved: bool, reason: str | None = None) -> bool:
    """Called when the user approves or rejects. Signals the waiting coroutine."""
    pending = _pending.get(approval_id)
    raw = await redis_client.get(f"{APPROVAL_KEY_PREFIX}{approval_id}")
    if not raw and not pending:
        await logger.awarning("approval_not_found", approval_id=approval_id)
        return False

    state = json.loads(raw) if raw else {
        "id": approval_id,
        "event_id": pending.event_id if pending else None,
        "tool_name": pending.tool_name if pending else "",
        "arguments": pending.arguments if pending else {},
        "conversation_id": pending.conversation_id if pending else "",
        "run_id": pending.run_id if pending else None,
        "agent_id": pending.agent_id if pending else None,
        "source": pending.source if pending else "hitl",
        "status": "pending",
        "reason": None,
    }

    if pending:
        pending.approved = approved
        pending.reject_reason = reason if not approved else None
        pending.event.set()

    status = "approved" if approved else "rejected"
    state["status"] = status
    state["reason"] = reason if not approved else None
    await redis_client.setex(
        f"{APPROVAL_KEY_PREFIX}{approval_id}",
        APPROVAL_TIMEOUT,
        json.dumps(state),
    )
    if state.get("event_id"):
        await event_bus.update_event_status(
            state["event_id"],
            status,
            result={"reason": reason} if reason else None,
        )

    await logger.ainfo("approval_resolved", approval_id=approval_id, approved=approved)
    return True


async def get_pending_approvals(
    conversation_id: str | None = None,
    run_id: str | None = None,
) -> list[dict]:
    """List pending approvals, optionally filtered by conversation."""
    approvals = []
    async for key in redis_client.scan_iter(f"{APPROVAL_KEY_PREFIX}*"):
        raw = await redis_client.get(key)
        if not raw:
            continue
        state = json.loads(raw)
        if state.get("status") != "pending":
            continue
        if conversation_id and state.get("conversation_id") != conversation_id:
            continue
        if run_id and state.get("run_id") != run_id:
            continue
        approvals.append(state)
    return approvals
