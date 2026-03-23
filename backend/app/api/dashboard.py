"""Dashboard WebSocket and REST endpoints for real-time agent monitoring."""
import asyncio
import json
from decimal import Decimal

import structlog
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, redis_client
from app.models.agent import Agent
from app.models.event import Event
from app.models.message import Message
from app.services.agent_orchestrator import (
    DASHBOARD_CHANNEL,
    get_all_agent_states,
)

logger = structlog.get_logger("dashboard")

router = APIRouter(tags=["dashboard"])


@router.get("/api/dashboard/agents")
async def dashboard_agents(db: AsyncSession = Depends(get_db)):
    """Get all agents with their current states."""
    result = await db.execute(select(Agent).where(Agent.is_active == True).order_by(Agent.name))
    agents = result.scalars().all()

    # Get live states from Redis
    live_states = await get_all_agent_states()

    return [
        {
            "id": str(a.id),
            "name": a.name,
            "description": a.description,
            "state": live_states.get(str(a.id), {}).get("state", a.state),
            "is_main": a.is_main,
            "llm_provider": a.llm_provider,
            "llm_model": a.llm_model,
        }
        for a in agents
    ]


@router.get("/api/dashboard/costs")
async def dashboard_costs(db: AsyncSession = Depends(get_db)):
    """Get cost summary."""
    result = await db.execute(
        select(
            func.count(Message.id).label("total_messages"),
            func.sum(Message.token_count).label("total_tokens"),
            func.sum(Message.cost_usd).label("total_cost"),
        ).where(Message.role == "assistant")
    )
    row = result.one()
    return {
        "total_messages": row.total_messages or 0,
        "total_tokens": int(row.total_tokens or 0),
        "total_cost": float(row.total_cost or 0),
    }


@router.get("/api/dashboard/events")
async def dashboard_events(limit: int = 20, db: AsyncSession = Depends(get_db)):
    """Get recent events for the dashboard feed."""
    result = await db.execute(
        select(Event).order_by(Event.created_at.desc()).limit(limit)
    )
    events = result.scalars().all()
    return [
        {
            "id": str(e.id),
            "event_type": e.event_type,
            "source": e.source,
            "status": e.status,
            "payload": e.payload,
            "created_at": e.created_at.isoformat(),
        }
        for e in events
    ]


@router.websocket("/ws/dashboard")
async def dashboard_websocket(websocket: WebSocket):
    """Real-time dashboard updates via Redis pub/sub."""
    await websocket.accept()
    await logger.ainfo("dashboard_ws_connected")

    pubsub = redis_client.pubsub()
    await pubsub.subscribe(DASHBOARD_CHANNEL)

    try:
        # Send initial state
        states = await get_all_agent_states()
        await websocket.send_json({
            "type": "initial_state",
            "agent_states": states,
        })

        # Stream updates
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message["type"] == "message":
                data = json.loads(message["data"])
                await websocket.send_json(data)
            else:
                # Send a ping to detect disconnection
                await asyncio.sleep(0.5)

    except WebSocketDisconnect:
        await logger.ainfo("dashboard_ws_disconnected")
    except Exception as e:
        await logger.aerror("dashboard_ws_error", error=str(e))
    finally:
        await pubsub.unsubscribe(DASHBOARD_CHANNEL)
        await pubsub.close()
