"""Event and HITL approval REST endpoints."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.event_bus.hitl import get_pending_approvals, resolve_approval
from app.models.event import Event
from app.schemas.event import ApprovalResponse, EventResponse

router = APIRouter(prefix="/api", tags=["events"])


@router.get("/events", response_model=list[EventResponse])
async def list_events(
    event_type: str | None = None,
    conversation_id: UUID | None = None,
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
):
    query = select(Event).order_by(Event.created_at.desc()).limit(limit)
    if event_type:
        query = query.where(Event.event_type == event_type)
    if conversation_id:
        query = query.where(Event.conversation_id == conversation_id)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/approvals/pending")
async def list_pending_approvals(conversation_id: str | None = None, run_id: str | None = None):
    pending = await get_pending_approvals(conversation_id=conversation_id, run_id=run_id)
    return [
        {
            "id": p["id"],
            "tool_name": p["tool_name"],
            "arguments": p["arguments"],
            "conversation_id": p["conversation_id"],
            "run_id": p.get("run_id"),
            "agent_id": p.get("agent_id"),
            "source": p.get("source"),
        }
        for p in pending
    ]


@router.post("/approvals/{approval_id}/approve")
async def approve(approval_id: str):
    ok = await resolve_approval(approval_id, approved=True)
    if not ok:
        raise HTTPException(404, "Approval not found or already resolved")
    return {"status": "approved"}


@router.post("/approvals/{approval_id}/reject")
async def reject(approval_id: str, body: ApprovalResponse | None = None):
    reason = body.reason if body else None
    ok = await resolve_approval(approval_id, approved=False, reason=reason)
    if not ok:
        raise HTTPException(404, "Approval not found or already resolved")
    return {"status": "rejected"}
