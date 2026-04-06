"""Background agent runs API."""
import asyncio
import os
import shutil
import tempfile
import time
from datetime import UTC
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.dependencies import async_session, get_db, redis_client
from app.event_bus.hitl import request_approval, wait_for_approval
from app.models.agent import Agent
from app.models.agent_run import AgentRun
from app.schemas.agent_run import AgentRunCreate, AgentRunResponse
from app.services.autonomous_execution import (
    AutonomousContext,
    run_autonomous_round,
)
from app.services.execution_prep import prepare_autonomous_resources
from app.services.agent_orchestrator import STATE_ERROR, STATE_EXECUTING, STATE_IDLE, STATE_THINKING, set_agent_state

logger = structlog.get_logger("runs")

router = APIRouter(prefix="/api/runs", tags=["runs"])

MAX_ROUNDS = 100
RUN_SIGNAL_PREFIX = "gini:run:signal:"
RUN_STATUS_AWAITING_APPROVAL = "awaiting_approval"


async def _check_run_signal(run_id: str) -> str | None:
    """Check if a run has a stop/pause signal. Returns 'stop', 'pause', or None."""
    return await redis_client.get(f"{RUN_SIGNAL_PREFIX}{run_id}")


async def _set_run_signal(run_id: str, signal: str | None):
    if signal:
        await redis_client.set(f"{RUN_SIGNAL_PREFIX}{run_id}", signal, ex=3600)
    else:
        await redis_client.delete(f"{RUN_SIGNAL_PREFIX}{run_id}")


def _failed_terminal_step(steps: list[dict]) -> dict | None:
    for step in reversed(steps):
        if step.get("type") == "tool_call":
            return step if step.get("success") is False else None
    return None


def _build_runtime_state(
    *,
    messages: list[dict],
    steps: list[dict],
    total_input: int,
    total_output: int,
    total_cost: float,
    next_round: int,
    workspace_path: str,
    elapsed_ms: float = 0.0,
) -> dict:
    return {
        "messages": messages,
        "steps": steps,
        "total_input": total_input,
        "total_output": total_output,
        "total_cost": total_cost,
        "next_round": next_round,
        "workspace_path": workspace_path,
        "elapsed_ms": elapsed_ms,
    }


@router.get("")
async def list_runs(
    status: str | None = None,
    agent_id: str | None = None,
    offset: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    query = select(AgentRun).options(selectinload(AgentRun.agent)).order_by(AgentRun.created_at.desc())
    count_query = select(func.count(AgentRun.id))

    if status:
        query = query.where(AgentRun.status == status)
        count_query = count_query.where(AgentRun.status == status)
    if agent_id:
        query = query.where(AgentRun.agent_id == UUID(agent_id))
        count_query = count_query.where(AgentRun.agent_id == UUID(agent_id))

    total = (await db.execute(count_query)).scalar_one()
    result = await db.execute(query.offset(offset).limit(limit))
    runs = result.scalars().all()

    return {
        "items": [AgentRunResponse.from_orm_model(r) for r in runs],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/{run_id}")
async def get_run(run_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AgentRun).options(selectinload(AgentRun.agent)).where(AgentRun.id == run_id)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(404, "Run not found")
    return AgentRunResponse.from_orm_model(run)


async def check_budget(agent: Agent, db: AsyncSession) -> str | None:
    """Check if agent has exceeded daily budget. Returns error message or None."""
    if agent.daily_budget_usd is None:
        return None
    from datetime import datetime
    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(func.coalesce(func.sum(AgentRun.cost_usd), 0))
        .where(AgentRun.agent_id == agent.id)
        .where(AgentRun.created_at >= today_start)
    )
    spent = float(result.scalar_one())
    if spent >= agent.daily_budget_usd:
        return f"Daily budget exceeded: ${spent:.4f} / ${agent.daily_budget_usd:.2f}"
    return None


@router.post("", status_code=201)
async def create_run(body: AgentRunCreate, db: AsyncSession = Depends(get_db)):
    agent = await db.get(Agent, body.agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")

    # Check budget
    budget_error = await check_budget(agent, db)
    if budget_error:
        raise HTTPException(429, budget_error)

    run = AgentRun(
        agent_id=body.agent_id,
        instructions=body.instructions,
        status="pending",
    )
    db.add(run)
    await db.commit()
    await db.refresh(run, ["agent"])

    response = AgentRunResponse.from_orm_model(run)

    # Fire background task
    asyncio.create_task(_execute_run(str(run.id), str(agent.id)))

    return response


@router.post("/{run_id}/retry", status_code=201)
async def retry_run(run_id: UUID, db: AsyncSession = Depends(get_db)):
    """Retry a failed run with the same agent and instructions."""
    result = await db.execute(
        select(AgentRun).options(selectinload(AgentRun.agent)).where(AgentRun.id == run_id)
    )
    old_run = result.scalar_one_or_none()
    if not old_run:
        raise HTTPException(404, "Run not found")
    if old_run.status not in ("failed",):
        raise HTTPException(400, "Only failed runs can be retried")

    new_run = AgentRun(
        agent_id=old_run.agent_id,
        instructions=old_run.instructions,
        status="pending",
    )
    db.add(new_run)
    await db.commit()
    await db.refresh(new_run, ["agent"])

    asyncio.create_task(_execute_run(str(new_run.id), str(old_run.agent_id)))

    return AgentRunResponse.from_orm_model(new_run)


@router.post("/{run_id}/stop")
async def stop_run(run_id: UUID, db: AsyncSession = Depends(get_db)):
    """Stop a running agent."""
    run = await db.get(AgentRun, run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    if run.status not in ("running", "pending", "paused", RUN_STATUS_AWAITING_APPROVAL):
        raise HTTPException(400, f"Cannot stop a {run.status} run")
    await _set_run_signal(str(run_id), "stop")
    return {"status": "stopping"}


@router.post("/{run_id}/pause")
async def pause_run(run_id: UUID, db: AsyncSession = Depends(get_db)):
    """Pause a running agent."""
    run = await db.get(AgentRun, run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    if run.status != "running":
        raise HTTPException(400, f"Cannot pause a {run.status} run")
    await _set_run_signal(str(run_id), "pause")
    return {"status": "pausing"}


@router.post("/{run_id}/resume")
async def resume_run(run_id: UUID, db: AsyncSession = Depends(get_db)):
    """Resume a paused agent from its persisted runtime state."""
    run = await db.get(AgentRun, run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    if run.status != "paused":
        raise HTTPException(400, f"Cannot resume a {run.status} run")
    await _set_run_signal(str(run_id), None)
    # Re-fire execution
    asyncio.create_task(_execute_run(str(run_id), str(run.agent_id)))
    return {"status": "resuming"}


async def _execute_run(run_id: str, agent_id: str) -> None:
    """Execute an agent run in the background."""
    await logger.ainfo("run_starting", run_id=run_id, agent_id=agent_id)
    start = time.perf_counter()
    steps: list[dict] = []
    total_input = 0
    total_output = 0
    total_cost = 0.0
    work_dir: str | None = None
    cleanup_workspace = True
    original_dir = os.getcwd()
    base_duration_ms = 0.0

    try:
        async with async_session() as db:
            result = await db.execute(
                select(AgentRun).options(selectinload(AgentRun.agent)).where(AgentRun.id == UUID(run_id))
            )
            run = result.scalar_one_or_none()
            if not run:
                await logger.aerror("run_not_found", run_id=run_id)
                return

            agent = run.agent
            restoring = run.status == "paused" and bool(run.runtime_state)
            runtime_state = run.runtime_state or {}
            run.status = "running"
            await db.commit()
    except Exception as e:
        await logger.aerror("run_init_error", run_id=run_id, error=str(e))
        return

    await set_agent_state(agent_id, STATE_THINKING)

    # Preserve the run workspace across pause/resume boundaries.
    if restoring and runtime_state.get("workspace_path") and os.path.isdir(runtime_state["workspace_path"]):
        work_dir = runtime_state["workspace_path"]
    else:
        work_dir = tempfile.mkdtemp(prefix=f"gini-run-{run_id[:8]}-")
    os.chdir(work_dir)

    try:
        instructions = run.instructions or f"You are {agent.name}. Execute your primary function and report the result."
        resources = await prepare_autonomous_resources(agent, include_approval_tools=True)

        if restoring:
            context = AutonomousContext(
                messages=runtime_state.get("messages") or [{"role": "user", "content": instructions}],
                steps=runtime_state.get("steps") or [],
                total_input_tokens=int(runtime_state.get("total_input", 0)),
                total_output_tokens=int(runtime_state.get("total_output", 0)),
                total_cost_usd=float(runtime_state.get("total_cost", 0.0)),
            )
            steps = runtime_state.get("steps") or []
            start_round = int(runtime_state.get("next_round", 0))
            base_duration_ms = float(runtime_state.get("elapsed_ms", 0.0))
        else:
            context = AutonomousContext(messages=[{"role": "user", "content": instructions}])
            start_round = 0
            base_duration_ms = 0.0
            async with async_session() as db:
                r = await db.get(AgentRun, UUID(run_id))
                if r:
                    r.runtime_state = _build_runtime_state(
                        messages=context.messages,
                        steps=context.steps,
                        total_input=context.total_input_tokens,
                        total_output=context.total_output_tokens,
                        total_cost=context.total_cost_usd,
                        next_round=0,
                        workspace_path=work_dir,
                        elapsed_ms=base_duration_ms,
                    )
                    await db.commit()

        for round_num in range(start_round, MAX_ROUNDS):
            # Check for stop/pause signals
            signal = await _check_run_signal(run_id)
            if signal == "stop":
                duration_ms = round(base_duration_ms + (time.perf_counter() - start) * 1000, 2)
                async with async_session() as db:
                    r = await db.get(AgentRun, UUID(run_id))
                    r.status = "failed"
                    r.error = "Stopped by user"
                    r.duration_ms = duration_ms
                    r.steps = context.steps
                    r.input_tokens = context.total_input_tokens
                    r.output_tokens = context.total_output_tokens
                    r.cost_usd = context.total_cost_usd
                    r.runtime_state = {}
                    await db.commit()
                await _set_run_signal(run_id, None)
                await set_agent_state(agent_id, STATE_IDLE)
                await logger.ainfo("run_stopped", run_id=run_id)
                return
            elif signal == "pause":
                async with async_session() as db:
                    r = await db.get(AgentRun, UUID(run_id))
                    r.status = "paused"
                    r.steps = context.steps
                    r.input_tokens = context.total_input_tokens
                    r.output_tokens = context.total_output_tokens
                    r.cost_usd = context.total_cost_usd
                    r.runtime_state = _build_runtime_state(
                        messages=context.messages,
                        steps=context.steps,
                        total_input=context.total_input_tokens,
                        total_output=context.total_output_tokens,
                        total_cost=context.total_cost_usd,
                        next_round=round_num,
                        workspace_path=work_dir,
                        elapsed_ms=round(base_duration_ms + (time.perf_counter() - start) * 1000, 2),
                    )
                    await db.commit()
                cleanup_workspace = False
                await set_agent_state(agent_id, STATE_IDLE)
                await logger.ainfo("run_paused", run_id=run_id)
                return

            await set_agent_state(agent_id, STATE_THINKING)

            async def request_tool_approval(tc: dict, _tool_policy) -> tuple[bool, str | None]:
                pending = await request_approval(
                    tool_name=tc["name"],
                    arguments=tc["arguments"],
                    run_id=run_id,
                    agent_id=agent_id,
                    source="run",
                )

                duration_ms = round(base_duration_ms + (time.perf_counter() - start) * 1000, 2)
                async with async_session() as db:
                    r = await db.get(AgentRun, UUID(run_id))
                    if r:
                        r.status = RUN_STATUS_AWAITING_APPROVAL
                        r.steps = list(context.steps)
                        r.input_tokens = context.total_input_tokens
                        r.output_tokens = context.total_output_tokens
                        r.cost_usd = context.total_cost_usd
                        r.runtime_state = _build_runtime_state(
                            messages=context.messages,
                            steps=context.steps,
                            total_input=context.total_input_tokens,
                            total_output=context.total_output_tokens,
                            total_cost=context.total_cost_usd,
                            next_round=round_num,
                            workspace_path=work_dir,
                            elapsed_ms=duration_ms,
                        )
                        await db.commit()

                await set_agent_state(
                    agent_id,
                    "awaiting_approval",
                    {"tool_name": tc["name"], "run_id": run_id},
                )
                approved = await wait_for_approval(pending, timeout=300)

                async with async_session() as db:
                    r = await db.get(AgentRun, UUID(run_id))
                    if r and r.status == RUN_STATUS_AWAITING_APPROVAL:
                        r.status = "running"
                        await db.commit()

                await set_agent_state(agent_id, STATE_EXECUTING if approved else STATE_THINKING)
                return approved, pending.reject_reason

            async def delegate_task_runner(agent_name: str, task: str) -> dict:
                from app.services.agent_orchestrator import get_agent_by_name, run_sub_agent

                sub_agent = await get_agent_by_name(agent_name)
                if not sub_agent:
                    return {
                        "success": False,
                        "content": f"Error: Agent '{agent_name}' not found.",
                        "cost_usd": 0.0,
                    }
                return await run_sub_agent(
                    agent=sub_agent,
                    task=task,
                    parent_conversation_id=f"run:{run_id}",
                )

            round_result = await run_autonomous_round(
                agent=agent,
                resources=resources,
                context=context,
                round_num=round_num,
                delegate_task_runner=delegate_task_runner,
                request_tool_approval=request_tool_approval,
                on_before_tools=lambda: set_agent_state(agent_id, STATE_EXECUTING),
            )

            # Update progress in DB so the UI can show steps
            async with async_session() as db:
                r = await db.get(AgentRun, UUID(run_id))
                r.steps = list(context.steps)
                r.input_tokens = context.total_input_tokens
                r.output_tokens = context.total_output_tokens
                r.cost_usd = context.total_cost_usd
                r.runtime_state = _build_runtime_state(
                    messages=context.messages,
                    steps=context.steps,
                    total_input=context.total_input_tokens,
                    total_output=context.total_output_tokens,
                    total_cost=context.total_cost_usd,
                    next_round=round_num + (0 if round_result.done else 1),
                    workspace_path=work_dir,
                    elapsed_ms=round(base_duration_ms + (time.perf_counter() - start) * 1000, 2),
                )
                await db.commit()

            if round_result.done:
                # Done
                duration_ms = round(base_duration_ms + (time.perf_counter() - start) * 1000, 2)
                failed_step = _failed_terminal_step(context.steps)
                async with async_session() as db:
                    r = await db.get(AgentRun, UUID(run_id))
                    if failed_step:
                        r.status = "failed"
                        r.error = str(
                            failed_step.get("error")
                            or failed_step.get("output")
                            or round_result.final_content
                        )[:2000]
                    else:
                        r.status = "done"
                        r.error = None
                    r.result = round_result.final_content
                    r.input_tokens = context.total_input_tokens
                    r.output_tokens = context.total_output_tokens
                    r.cost_usd = context.total_cost_usd
                    r.duration_ms = duration_ms
                    r.steps = context.steps
                    r.runtime_state = {}
                    await db.commit()

                if failed_step:
                    await set_agent_state(agent_id, STATE_ERROR)
                    await logger.awarning(
                        "run_completed_with_failed_tool",
                        run_id=run_id,
                        agent=agent.name,
                        cost=context.total_cost_usd,
                        duration_ms=duration_ms,
                        failed_tool=failed_step.get("tool"),
                    )
                else:
                    await set_agent_state(agent_id, STATE_IDLE)
                    await logger.ainfo("run_completed", run_id=run_id, agent=agent.name, cost=context.total_cost_usd, duration_ms=duration_ms)
                return

        # Exceeded rounds
        duration_ms = round(base_duration_ms + (time.perf_counter() - start) * 1000, 2)
        async with async_session() as db:
            r = await db.get(AgentRun, UUID(run_id))
            r.status = "failed"
            r.error = f"Exceeded max rounds ({MAX_ROUNDS})"
            r.input_tokens = context.total_input_tokens
            r.output_tokens = context.total_output_tokens
            r.cost_usd = context.total_cost_usd
            r.duration_ms = duration_ms
            r.steps = context.steps
            r.runtime_state = {}
            await db.commit()

        await set_agent_state(agent_id, STATE_ERROR)

    except Exception as e:
        duration_ms = round(base_duration_ms + (time.perf_counter() - start) * 1000, 2)
        await logger.aerror("run_failed", run_id=run_id, error=str(e))
        async with async_session() as db:
            r = await db.get(AgentRun, UUID(run_id))
            if r:
                r.status = "failed"
                r.error = str(e)[:2000]
                r.duration_ms = duration_ms
                r.steps = context.steps if "context" in locals() else steps
                r.input_tokens = context.total_input_tokens if "context" in locals() else total_input
                r.output_tokens = context.total_output_tokens if "context" in locals() else total_output
                r.cost_usd = context.total_cost_usd if "context" in locals() else total_cost
                r.runtime_state = {}
                await db.commit()

        await set_agent_state(agent_id, STATE_ERROR)
    finally:
        os.chdir(original_dir)
        if cleanup_workspace and work_dir:
            shutil.rmtree(work_dir, ignore_errors=True)
