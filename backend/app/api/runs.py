"""Background agent runs API."""
import asyncio
import os
import shutil
import tempfile
import time
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.dependencies import get_db, async_session, redis_client
from app.models.agent import Agent
from app.models.agent_run import AgentRun
from app.schemas.agent_run import AgentRunCreate, AgentRunResponse
from app.services.llm_gateway import llm_gateway, LLMResponse
from app.services.skill_executor import get_assembled_prompt_with_credentials
from app.services.tool_runner import execute_tool
from app.services.agent_orchestrator import set_agent_state, STATE_THINKING, STATE_EXECUTING, STATE_IDLE, STATE_ERROR
from app.tools.registry import get_all_tool_specs

logger = structlog.get_logger("runs")

router = APIRouter(prefix="/api/runs", tags=["runs"])

MAX_ROUNDS = 100
RUN_SIGNAL_PREFIX = "gini:run:signal:"


async def _check_run_signal(run_id: str) -> str | None:
    """Check if a run has a stop/pause signal. Returns 'stop', 'pause', or None."""
    return await redis_client.get(f"{RUN_SIGNAL_PREFIX}{run_id}")


async def _set_run_signal(run_id: str, signal: str | None):
    if signal:
        await redis_client.set(f"{RUN_SIGNAL_PREFIX}{run_id}", signal, ex=3600)
    else:
        await redis_client.delete(f"{RUN_SIGNAL_PREFIX}{run_id}")


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
    from datetime import datetime, timezone, timedelta
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
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
    if run.status not in ("running", "pending", "paused"):
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
    """Resume a paused agent."""
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
            run.status = "running"
            await db.commit()
    except Exception as e:
        await logger.aerror("run_init_error", run_id=run_id, error=str(e))
        return

    await set_agent_state(agent_id, STATE_THINKING)

    # Run in a temp directory so file writes don't pollute the app dir
    work_dir = tempfile.mkdtemp(prefix=f"gini-run-{run_id[:8]}-")
    original_dir = os.getcwd()
    os.chdir(work_dir)

    try:
        # Build prompt (with credentials injected for background execution)
        instructions = run.instructions or f"You are {agent.name}. Execute your primary function and report the result."
        system_prompt = await get_assembled_prompt_with_credentials(agent)

        tool_specs = await get_all_tool_specs()
        messages = [{"role": "user", "content": instructions}]

        total_input = 0
        total_output = 0
        total_cost = 0.0
        steps = []

        for round_num in range(MAX_ROUNDS):
            # Check for stop/pause signals
            signal = await _check_run_signal(run_id)
            if signal == "stop":
                duration_ms = round((time.perf_counter() - start) * 1000, 2)
                async with async_session() as db:
                    r = await db.get(AgentRun, UUID(run_id))
                    r.status = "failed"
                    r.error = "Stopped by user"
                    r.duration_ms = duration_ms
                    r.steps = steps
                    r.input_tokens = total_input
                    r.output_tokens = total_output
                    r.cost_usd = total_cost
                    await db.commit()
                await _set_run_signal(run_id, None)
                await set_agent_state(agent_id, STATE_IDLE)
                await logger.ainfo("run_stopped", run_id=run_id)
                return
            elif signal == "pause":
                async with async_session() as db:
                    r = await db.get(AgentRun, UUID(run_id))
                    r.status = "paused"
                    r.steps = steps
                    r.input_tokens = total_input
                    r.output_tokens = total_output
                    r.cost_usd = total_cost
                    await db.commit()
                await set_agent_state(agent_id, STATE_IDLE)
                await logger.ainfo("run_paused", run_id=run_id)
                return  # execution stops; resume will re-fire _execute_run

            await set_agent_state(agent_id, STATE_THINKING)

            response: LLMResponse = await llm_gateway.call_with_tools(
                messages=messages,
                system_prompt=system_prompt,
                tools=tool_specs if tool_specs else None,
                provider=agent.llm_provider,
                model=agent.llm_model,
                temperature=agent.temperature,
                max_tokens=agent.max_tokens,
            )

            total_input += response.input_tokens
            total_output += response.output_tokens
            total_cost += response.cost_usd

            steps.append({
                "type": "llm_call",
                "round": round_num,
                "content": (response.content or "")[:1000],
                "tool_calls": len(response.tool_calls) if response.tool_calls else 0,
                "tokens": response.input_tokens + response.output_tokens,
            })

            # Update progress in DB so the UI can show steps
            async with async_session() as db:
                r = await db.get(AgentRun, UUID(run_id))
                r.steps = list(steps)
                r.input_tokens = total_input
                r.output_tokens = total_output
                r.cost_usd = total_cost
                await db.commit()

            if not response.tool_calls:
                # Done
                duration_ms = round((time.perf_counter() - start) * 1000, 2)
                async with async_session() as db:
                    r = await db.get(AgentRun, UUID(run_id))
                    r.status = "done"
                    r.result = response.content
                    r.input_tokens = total_input
                    r.output_tokens = total_output
                    r.cost_usd = total_cost
                    r.duration_ms = duration_ms
                    r.steps = steps
                    await db.commit()

                await set_agent_state(agent_id, STATE_IDLE)
                await logger.ainfo("run_completed", run_id=run_id, agent=agent.name, cost=total_cost, duration_ms=duration_ms)
                return

            # Execute tools
            await set_agent_state(agent_id, STATE_EXECUTING)

            assistant_content = []
            if response.content:
                assistant_content.append({"type": "text", "text": response.content})
            for tc in response.tool_calls:
                assistant_content.append({
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": tc["name"],
                    "input": tc["arguments"],
                })
            messages.append({"role": "assistant", "content": assistant_content})

            tool_results_content = []
            for tc in response.tool_calls:
                tool_result = await execute_tool(tc["name"], tc["arguments"], use_sandbox=True, allow_network=True)
                tool_output = tool_result.output if tool_result.success else f"Error: {tool_result.error}"
                tool_results_content.append({
                    "type": "tool_result",
                    "tool_use_id": tc["id"],
                    "content": tool_output[:10000],
                })
                steps.append({
                    "type": "tool_call",
                    "tool": tc["name"],
                    "arguments": tc["arguments"],
                    "success": tool_result.success,
                    "output": (tool_result.output or "")[:2000],
                    "error": tool_result.error,
                })

            messages.append({"role": "user", "content": tool_results_content})

            # Update progress after tool calls
            async with async_session() as db:
                r = await db.get(AgentRun, UUID(run_id))
                r.steps = list(steps)
                r.input_tokens = total_input
                r.output_tokens = total_output
                r.cost_usd = total_cost
                await db.commit()

        # Exceeded rounds
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        async with async_session() as db:
            r = await db.get(AgentRun, UUID(run_id))
            r.status = "failed"
            r.error = f"Exceeded max rounds ({MAX_ROUNDS})"
            r.input_tokens = total_input
            r.output_tokens = total_output
            r.cost_usd = total_cost
            r.duration_ms = duration_ms
            r.steps = steps
            await db.commit()

        await set_agent_state(agent_id, STATE_ERROR)

    except Exception as e:
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        await logger.aerror("run_failed", run_id=run_id, error=str(e))
        async with async_session() as db:
            r = await db.get(AgentRun, UUID(run_id))
            if r:
                r.status = "failed"
                r.error = str(e)[:2000]
                r.duration_ms = duration_ms
                r.steps = steps if 'steps' in dir() else []
                await db.commit()

        await set_agent_state(agent_id, STATE_ERROR)
    finally:
        os.chdir(original_dir)
        shutil.rmtree(work_dir, ignore_errors=True)

