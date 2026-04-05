"""Agent orchestrator — manages agent lifecycle, delegation, and state tracking."""
import time
from collections.abc import Callable
from uuid import UUID

import structlog
from sqlalchemy import select, update

from app.dependencies import async_session, redis_client
from app.event_bus.bus import event_bus
from app.event_bus.events import EventTypes
from app.models.agent import Agent
from app.models.agent_run import AgentRun
from app.services.autonomous_execution import (
    AutonomousContext,
    run_autonomous_round,
)
from app.services.execution_prep import prepare_autonomous_resources

logger = structlog.get_logger("orchestrator")

# Agent states
STATE_IDLE = "idle"
STATE_THINKING = "thinking"
STATE_EXECUTING = "executing"
STATE_DELEGATING = "delegating"
STATE_DONE = "done"
STATE_ERROR = "error"

# Redis key for dashboard state
AGENT_STATE_KEY = "gini:agent_states"
DASHBOARD_CHANNEL = "gini:dashboard"

MAX_DELEGATION_ROUNDS = 100


async def set_agent_state(agent_id: str, state: str, metadata: dict | None = None) -> None:
    """Update agent state in DB and broadcast to dashboard."""
    # Update DB
    async with async_session() as db:
        await db.execute(
            update(Agent).where(Agent.id == UUID(agent_id)).values(state=state)
        )
        await db.commit()

    # Store in Redis for quick dashboard reads
    import json
    state_data = {"state": state, "agent_id": agent_id, **(metadata or {})}
    await redis_client.hset(AGENT_STATE_KEY, agent_id, json.dumps(state_data))

    # Broadcast to dashboard subscribers
    await redis_client.publish(DASHBOARD_CHANNEL, json.dumps({
        "type": "agent_state_change",
        "agent_id": agent_id,
        "state": state,
        **(metadata or {}),
    }))


async def get_all_agent_states() -> dict:
    """Get current state of all agents from Redis."""
    import json
    raw = await redis_client.hgetall(AGENT_STATE_KEY)
    return {k: json.loads(v) for k, v in raw.items()}


async def broadcast_dashboard_event(event_data: dict) -> None:
    """Send an event to all dashboard WebSocket subscribers."""
    import json
    await redis_client.publish(DASHBOARD_CHANNEL, json.dumps(event_data))


async def get_agent_by_name(name: str) -> Agent | None:
    """Look up an agent by name."""
    async with async_session() as db:
        result = await db.execute(select(Agent).where(Agent.name == name))
        return result.scalar_one_or_none()


async def run_sub_agent(
    agent: Agent,
    task: str,
    parent_conversation_id: str,
    on_chunk: Callable | None = None,
) -> dict:
    """Run a sub-agent to completion on a task. Returns the result.

    Args:
        agent: The sub-agent to run
        task: The task description/prompt
        parent_conversation_id: For event correlation
        on_chunk: Optional callback for streaming updates
    """
    start = time.perf_counter()

    # Create an AgentRun record so it shows in the Runs dashboard
    async with async_session() as db:
        run_record = AgentRun(
            agent_id=agent.id,
            instructions=task[:2000],
            status="running",
        )
        db.add(run_record)
        await db.commit()
        await db.refresh(run_record)
        run_id = run_record.id

    await set_agent_state(str(agent.id), STATE_THINKING, {"task": task[:200]})
    await event_bus.publish(
        EventTypes.AGENT_STARTED,
        payload={"agent_name": agent.name, "task": task[:500]},
        conversation_id=parent_conversation_id,
        source=f"agent:{agent.name}",
    )

    resources = await prepare_autonomous_resources(agent)
    context = AutonomousContext(messages=[{"role": "user", "content": task}])

    try:
        for round_num in range(MAX_DELEGATION_ROUNDS):
            await set_agent_state(str(agent.id), STATE_THINKING)

            async def delegate_task_runner(agent_name: str, task_text: str) -> dict:
                sub_agent = await get_agent_by_name(agent_name)
                if not sub_agent:
                    return {
                        "success": False,
                        "content": f"Error: Agent '{agent_name}' not found.",
                        "cost_usd": 0.0,
                    }
                return await run_sub_agent(
                    agent=sub_agent,
                    task=task_text,
                    parent_conversation_id=parent_conversation_id,
                )

            round_result = await run_autonomous_round(
                agent=agent,
                resources=resources,
                context=context,
                round_num=round_num,
                delegate_task_runner=delegate_task_runner,
                on_before_tools=lambda: set_agent_state(str(agent.id), STATE_EXECUTING),
            )

            if round_result.done:
                duration_ms = round((time.perf_counter() - start) * 1000, 2)

                # Update run record
                async with async_session() as db:
                    r = await db.get(AgentRun, run_id)
                    if r:
                        r.status = "done"
                        r.result = round_result.final_content
                        r.input_tokens = context.total_input_tokens
                        r.output_tokens = context.total_output_tokens
                        r.cost_usd = context.total_cost_usd
                        r.duration_ms = duration_ms
                        await db.commit()

                await set_agent_state(str(agent.id), STATE_IDLE)
                await event_bus.publish(
                    EventTypes.AGENT_COMPLETED,
                    payload={
                        "agent_name": agent.name,
                        "input_tokens": context.total_input_tokens,
                        "output_tokens": context.total_output_tokens,
                        "cost_usd": context.total_cost_usd,
                        "duration_ms": duration_ms,
                    },
                    conversation_id=parent_conversation_id,
                    source=f"agent:{agent.name}",
                )

                return {
                    "success": True,
                    "content": round_result.final_content,
                    "agent_name": agent.name,
                    "model": round_result.response.model,
                    "input_tokens": context.total_input_tokens,
                    "output_tokens": context.total_output_tokens,
                    "cost_usd": context.total_cost_usd,
                    "duration_ms": duration_ms,
                }

        # Exhausted rounds
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        async with async_session() as db:
            r = await db.get(AgentRun, run_id)
            if r:
                r.status = "failed"
                r.error = f"Exceeded max rounds ({MAX_DELEGATION_ROUNDS})"
                r.cost_usd = context.total_cost_usd
                r.duration_ms = duration_ms
                await db.commit()

        await set_agent_state(str(agent.id), STATE_ERROR)
        return {
            "success": False,
            "content": f"Sub-agent {agent.name} exceeded max rounds ({MAX_DELEGATION_ROUNDS})",
            "agent_name": agent.name,
            "cost_usd": context.total_cost_usd,
        }

    except Exception as e:
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        async with async_session() as db:
            r = await db.get(AgentRun, run_id)
            if r:
                r.status = "failed"
                r.error = str(e)[:2000]
                r.cost_usd = context.total_cost_usd
                r.duration_ms = duration_ms
                await db.commit()

        await set_agent_state(str(agent.id), STATE_ERROR)
        await logger.aerror("sub_agent_error", agent=agent.name, error=str(e))
        return {
            "success": False,
            "content": f"Sub-agent error: {str(e)}",
            "agent_name": agent.name,
            "cost_usd": context.total_cost_usd,
        }
