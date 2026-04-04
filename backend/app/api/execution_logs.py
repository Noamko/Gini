"""Execution trace and cost breakdown endpoints."""
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import String, cast, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.agent import Agent
from app.models.agent_run import AgentRun
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
        "steps": [ExecutionLogResponse.from_orm_model(log) for log in logs],
        "total_duration_ms": sum(log.duration_ms for log in logs),
        "total_cost_usd": sum(log.cost_usd for log in logs),
        "total_input_tokens": sum(log.input_tokens for log in logs),
        "total_output_tokens": sum(log.output_tokens for log in logs),
    }


@router.get("/api/costs")
async def cost_summary(db: AsyncSession = Depends(get_db)):
    """Overall cost summary from execution logs + agent runs."""
    # Execution logs (chat interactions)
    r1 = await db.execute(
        select(
            func.count(distinct(ExecutionLog.trace_id)).label("traces"),
            func.sum(ExecutionLog.input_tokens).label("input"),
            func.sum(ExecutionLog.output_tokens).label("output"),
            func.sum(ExecutionLog.cost_usd).label("cost"),
            func.sum(ExecutionLog.duration_ms).label("duration"),
        )
    )
    logs = r1.one()

    # Agent runs (background runs + delegations)
    r2 = await db.execute(
        select(
            func.count(AgentRun.id).label("runs"),
            func.sum(AgentRun.input_tokens).label("input"),
            func.sum(AgentRun.output_tokens).label("output"),
            func.sum(AgentRun.cost_usd).label("cost"),
            func.sum(AgentRun.duration_ms).label("duration"),
        ).where(AgentRun.status.in_(["done", "failed"]))
    )
    runs = r2.one()

    return {
        "total_traces": (logs.traces or 0) + (runs.runs or 0),
        "total_steps": 0,
        "total_input_tokens": int((logs.input or 0) + (runs.input or 0)),
        "total_output_tokens": int((logs.output or 0) + (runs.output or 0)),
        "total_cost": float((logs.cost or 0) + (runs.cost or 0)),
        "total_duration_ms": float((logs.duration or 0) + (runs.duration or 0)),
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

    # Get from execution_logs
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
    )
    merged: dict[str, dict] = {}
    for r in result.all():
        merged[r.group_key] = {
            "group": r.group_key,
            "count": r.count or 0,
            "input_tokens": int(r.input_tokens or 0),
            "output_tokens": int(r.output_tokens or 0),
            "cost_usd": float(r.cost_usd or 0),
            "duration_ms": float(r.duration_ms or 0),
        }

    # For agent breakdown, also include agent_runs data
    if group_by == "agent":
        runs_result = await db.execute(
            select(
                Agent.name.label("agent_name"),
                func.count(AgentRun.id).label("count"),
                func.sum(AgentRun.input_tokens).label("input_tokens"),
                func.sum(AgentRun.output_tokens).label("output_tokens"),
                func.sum(AgentRun.cost_usd).label("cost_usd"),
                func.sum(AgentRun.duration_ms).label("duration_ms"),
            )
            .join(Agent, AgentRun.agent_id == Agent.id)
            .where(AgentRun.status.in_(["done", "failed"]))
            .group_by(Agent.name)
        )
        for r in runs_result.all():
            name = r.agent_name
            if name in merged:
                merged[name]["count"] += r.count or 0
                merged[name]["input_tokens"] += int(r.input_tokens or 0)
                merged[name]["output_tokens"] += int(r.output_tokens or 0)
                merged[name]["cost_usd"] += float(r.cost_usd or 0)
                merged[name]["duration_ms"] += float(r.duration_ms or 0)
            else:
                merged[name] = {
                    "group": name,
                    "count": r.count or 0,
                    "input_tokens": int(r.input_tokens or 0),
                    "output_tokens": int(r.output_tokens or 0),
                    "cost_usd": float(r.cost_usd or 0),
                    "duration_ms": float(r.duration_ms or 0),
                }

    return sorted(merged.values(), key=lambda x: x["cost_usd"], reverse=True)
