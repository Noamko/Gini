"""Scheduler — checks for due schedules and fires agent runs."""
import asyncio
from datetime import datetime, timezone

import structlog
from croniter import croniter
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.dependencies import async_session
from app.models.schedule import Schedule
from app.models.agent_run import AgentRun

logger = structlog.get_logger("scheduler")

CHECK_INTERVAL = 30  # seconds


def compute_next_run(cron_expression: str, after: datetime | None = None) -> datetime | None:
    """Compute the next run time from a cron expression. Returns None if invalid."""
    try:
        base = after or datetime.now(timezone.utc)
        cron = croniter(cron_expression, base)
        return cron.get_next(datetime).replace(tzinfo=timezone.utc)
    except (ValueError, KeyError):
        return None


class Scheduler:
    def __init__(self):
        self._running = False

    async def start(self):
        self._running = True
        await logger.ainfo("scheduler_started", interval=CHECK_INTERVAL)
        asyncio.create_task(self._loop())

    async def stop(self):
        self._running = False

    async def _loop(self):
        while self._running:
            try:
                await self._check_schedules()
            except Exception as e:
                await logger.aerror("scheduler_error", error=str(e))
            await asyncio.sleep(CHECK_INTERVAL)

    async def _check_schedules(self):
        now = datetime.now(timezone.utc)

        async with async_session() as db:
            result = await db.execute(
                select(Schedule)
                .options(selectinload(Schedule.agent))
                .where(Schedule.enabled == True)
                .where(Schedule.next_run_at <= now)
            )
            due_schedules = result.scalars().all()

            for schedule in due_schedules:
                await logger.ainfo(
                    "schedule_triggered",
                    schedule_id=str(schedule.id),
                    name=schedule.name,
                    agent=schedule.agent.name if schedule.agent else "?",
                )

                # Create an agent run
                run = AgentRun(
                    agent_id=schedule.agent_id,
                    instructions=schedule.instructions,
                    status="pending",
                )
                db.add(run)

                # Update schedule timestamps
                schedule.last_run_at = now
                schedule.next_run_at = compute_next_run(schedule.cron_expression, after=now)

                await db.commit()
                await db.refresh(run)

                # Fire the background execution
                from app.api.runs import _execute_run
                asyncio.create_task(_execute_run(str(run.id), str(schedule.agent_id)))


scheduler = Scheduler()
