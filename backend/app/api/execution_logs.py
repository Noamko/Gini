"""Execution trace and cost breakdown endpoints."""
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, distinct, cast, String
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.execution_log import ExecutionLog
from app.schemas.execution_log import ExecutionLogResponse, TraceSummary

router = APIRouter(tags=["traces"])


@router.get("/api/traces")
async def list_traces(
    conversation_id: UUID | None = None,
    agent_name: str | None = None,
    limit: int = Query(30, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List trace summaries, most recent first."""
    # Subquery: aggregate per trace_id
    sub = (
        select(
            ExecutionLog.trace_id,
            func.min(cast(ExecutionLog.conversation_id, String)).label("conversation_id"),
            func.min(ExecutionLog.agent_name).label("agent_name"),
            func.count(ExecutionLog.id).label("step_count"),
            func.sum(ExecutionLog.duration_ms).label("total_duration_ms"),
            func.sum(ExecutionLog.input_tokens).label("total_input_tokens"),
            func.sum(ExecutionLog.output_tokens).label("total_output_tokens"),
            func.sum(ExecutionLog.cost_usd).label("total_cost_usd"),
            func.min(ExecutionLog.created_at).label("started_at"),
            func.array_agg(distinct(ExecutionLog.step_type)).label("step_types"),
        )
        .group_by(ExecutionLog.trace_id)
    )

    if conversation_id:
        sub = sub.where(ExecutionLog.conversation_id == conversation_id)
    if agent_name:
        sub = sub.where(ExecutionLog.agent_name == agent_name)

    sub = sub.subquery()

    # Count total traces
    count_result = await db.execute(select(func.count()).select_from(sub))
    total = count_result.scalar() or 0

    # Fetch page
    stmt = (
        select(sub)
        .order_by(sub.c.started_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.all()

    items = [
        TraceSummary(
            trace_id=r.trace_id,
            conversation_id=r.conversation_id,
            agent_name=r.agent_name,
            step_count=r.step_count,
            total_duration_ms=float(r.total_duration_ms or 0),
            total_input_tokens=int(r.total_input_tokens or 0),
            total_output_tokens=int(r.total_output_tokens or 0),
            total_cost_usd=float(r.total_cost_usd or 0),
            started_at=r.started_at,
            step_types=r.step_types or [],
        )
        for r in rows
    ]
    return {"items": items, "total": total, "offset": offset, "limit": limit}


@router.get("/api/traces/{trace_id}")
async def get_trace(trace_id: str, db: AsyncSession = Depends(get_db)):
    """Get all steps for a specific trace."""
    result = await db.execute(
        select(ExecutionLog)
        .where(ExecutionLog.trace_id == trace_id)
        .order_by(ExecutionLog.step_order.asc())
    )
    logs = result.scalars().all()
    return {
        "trace_id": trace_id,
        "steps": [ExecutionLogResponse.from_orm_model(l) for l in logs],
        "total_duration_ms": sum(l.duration_ms for l in logs),
        "total_cost_usd": sum(l.cost_usd for l in logs),
        "total_input_tokens": sum(l.input_tokens for l in logs),
        "total_output_tokens": sum(l.output_tokens for l in logs),
    }


@router.get("/api/costs")
async def cost_summary(db: AsyncSession = Depends(get_db)):
    """Overall cost summary from execution logs."""
    result = await db.execute(
        select(
            func.count(distinct(ExecutionLog.trace_id)).label("total_traces"),
            func.count(ExecutionLog.id).label("total_steps"),
            func.sum(ExecutionLog.input_tokens).label("total_input_tokens"),
            func.sum(ExecutionLog.output_tokens).label("total_output_tokens"),
            func.sum(ExecutionLog.cost_usd).label("total_cost"),
            func.sum(ExecutionLog.duration_ms).label("total_duration_ms"),
        )
    )
    row = result.one()
    return {
        "total_traces": row.total_traces or 0,
        "total_steps": row.total_steps or 0,
        "total_input_tokens": int(row.total_input_tokens or 0),
        "total_output_tokens": int(row.total_output_tokens or 0),
        "total_cost": float(row.total_cost or 0),
        "total_duration_ms": float(row.total_duration_ms or 0),
    }


@router.get("/api/costs/breakdown")
async def cost_breakdown(
    group_by: str = Query("model", regex="^(model|agent|step_type)$"),
    db: AsyncSession = Depends(get_db),
):
    """Cost breakdown grouped by model, agent, or step_type."""
    group_col = {
        "model": ExecutionLog.model,
        "agent": ExecutionLog.agent_name,
        "step_type": ExecutionLog.step_type,
    }[group_by]

    result = await db.execute(
        select(
            group_col.label("group_key"),
            func.count(ExecutionLog.id).label("count"),
            func.sum(ExecutionLog.input_tokens).label("input_tokens"),
            func.sum(ExecutionLog.output_tokens).label("output_tokens"),
            func.sum(ExecutionLog.cost_usd).label("cost_usd"),
            func.sum(ExecutionLog.duration_ms).label("duration_ms"),
        )
        .where(group_col.isnot(None))
        .group_by(group_col)
        .order_by(func.sum(ExecutionLog.cost_usd).desc())
    )
    rows = result.all()
    return [
        {
            "group": r.group_key,
            "count": r.count,
            "input_tokens": int(r.input_tokens or 0),
            "output_tokens": int(r.output_tokens or 0),
            "cost_usd": float(r.cost_usd or 0),
            "duration_ms": float(r.duration_ms or 0),
        }
        for r in rows
    ]
