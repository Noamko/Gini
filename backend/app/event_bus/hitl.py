"""Human-in-the-Loop approval flow.

Manages pending approvals using asyncio.Event for signaling.
The chat WebSocket handler sends approval requests and listens for responses.
"""
import asyncio
import uuid
from dataclasses import dataclass

import structlog

from app.event_bus.bus import event_bus
from app.event_bus.events import EventTypes

logger = structlog.get_logger("hitl")

APPROVAL_TIMEOUT = 300  # 5 minutes


@dataclass
class PendingApproval:
    id: str
    tool_name: str
    arguments: dict
    conversation_id: str
    event: asyncio.Event
    approved: bool | None = None
    reject_reason: str | None = None


# In-memory store of pending approvals keyed by approval_id
_pending: dict[str, PendingApproval] = {}


async def request_approval(
    tool_name: str,
    arguments: dict,
    conversation_id: str,
) -> PendingApproval:
    """Create an approval request and return a PendingApproval that can be awaited."""
    approval_id = str(uuid.uuid4())

    pending = PendingApproval(
        id=approval_id,
        tool_name=tool_name,
        arguments=arguments,
        conversation_id=conversation_id,
        event=asyncio.Event(),
    )
    _pending[approval_id] = pending

    # Persist the event
    await event_bus.publish(
        event_type=EventTypes.APPROVAL_REQUESTED,
        payload={"tool_name": tool_name, "arguments": arguments},
        correlation_id=approval_id,
        conversation_id=conversation_id,
        source="hitl",
    )

    await logger.ainfo("approval_requested", approval_id=approval_id, tool=tool_name)
    return pending


async def wait_for_approval(pending: PendingApproval, timeout: float = APPROVAL_TIMEOUT) -> bool:
    """Wait for user to approve or reject. Returns True if approved."""
    try:
        await asyncio.wait_for(pending.event.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        await logger.awarn("approval_timeout", approval_id=pending.id)
        pending.approved = False
        pending.reject_reason = "Approval timed out"
        await event_bus.update_event_status(pending.id, "timeout")
    finally:
        _pending.pop(pending.id, None)

    return pending.approved is True


async def resolve_approval(approval_id: str, approved: bool, reason: str | None = None) -> bool:
    """Called when the user approves or rejects. Signals the waiting coroutine."""
    pending = _pending.get(approval_id)
    if not pending:
        await logger.awarn("approval_not_found", approval_id=approval_id)
        return False

    pending.approved = approved
    pending.reject_reason = reason if not approved else None
    pending.event.set()

    event_type = EventTypes.APPROVAL_GRANTED if approved else EventTypes.APPROVAL_REJECTED
    status = "approved" if approved else "rejected"
    await event_bus.update_event_status(
        pending.id,
        status,
        result={"reason": reason} if reason else None,
    )

    await logger.ainfo("approval_resolved", approval_id=approval_id, approved=approved)
    return True


def get_pending_approvals(conversation_id: str | None = None) -> list[PendingApproval]:
    """List pending approvals, optionally filtered by conversation."""
    if conversation_id:
        return [p for p in _pending.values() if p.conversation_id == conversation_id]
    return list(_pending.values())
