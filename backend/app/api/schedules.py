"""Schedule CRUD API."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.dependencies import get_db
from app.models.agent import Agent
from app.models.schedule import Schedule
from app.schemas.schedule import ScheduleCreate, ScheduleResponse, ScheduleUpdate
from app.services.scheduler import compute_next_run

router = APIRouter(prefix="/api/schedules", tags=["schedules"])


@router.get("")
async def list_schedules(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Schedule).options(selectinload(Schedule.agent), selectinload(Schedule.workflow)).order_by(Schedule.created_at.desc())
    )
    schedules = result.scalars().all()
    return {"items": [ScheduleResponse.from_orm_model(s) for s in schedules]}


@router.get("/{schedule_id}")
async def get_schedule(schedule_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Schedule).options(selectinload(Schedule.agent), selectinload(Schedule.workflow)).where(Schedule.id == schedule_id)
    )
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(404, "Schedule not found")
    return ScheduleResponse.from_orm_model(schedule)


@router.post("", status_code=201)
async def create_schedule(body: ScheduleCreate, db: AsyncSession = Depends(get_db)):
    if not body.agent_id and not body.workflow_id:
        raise HTTPException(400, "Either agent_id or workflow_id is required")
    if body.agent_id:
        agent = await db.get(Agent, body.agent_id)
        if not agent:
            raise HTTPException(404, "Agent not found")
    if body.workflow_id:
        from app.models.workflow import Workflow
        wf = await db.get(Workflow, body.workflow_id)
        if not wf:
            raise HTTPException(404, "Workflow not found")

    next_run = compute_next_run(body.cron_expression)
    if next_run is None:
        raise HTTPException(400, f"Invalid cron expression: {body.cron_expression}")

    schedule = Schedule(
        agent_id=body.agent_id,
        workflow_id=body.workflow_id,
        name=body.name,
        cron_expression=body.cron_expression,
        instructions=body.instructions,
        enabled=body.enabled,
        next_run_at=next_run,
    )
    db.add(schedule)
    await db.commit()
    await db.refresh(schedule, ["agent", "workflow"])
    return ScheduleResponse.from_orm_model(schedule)


@router.put("/{schedule_id}")
async def update_schedule(schedule_id: UUID, body: ScheduleUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Schedule).options(selectinload(Schedule.agent), selectinload(Schedule.workflow)).where(Schedule.id == schedule_id)
    )
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(404, "Schedule not found")

    if body.name is not None:
        schedule.name = body.name
    if body.instructions is not None:
        schedule.instructions = body.instructions
    if body.enabled is not None:
        schedule.enabled = body.enabled
    if body.cron_expression is not None:
        next_run = compute_next_run(body.cron_expression)
        if next_run is None:
            raise HTTPException(400, f"Invalid cron expression: {body.cron_expression}")
        schedule.cron_expression = body.cron_expression
        schedule.next_run_at = next_run

    await db.commit()
    await db.refresh(schedule, ["agent", "workflow"])
    return ScheduleResponse.from_orm_model(schedule)


@router.delete("/{schedule_id}", status_code=204)
async def delete_schedule(schedule_id: UUID, db: AsyncSession = Depends(get_db)):
    schedule = await db.get(Schedule, schedule_id)
    if not schedule:
        raise HTTPException(404, "Schedule not found")
    await db.delete(schedule)
    await db.commit()
