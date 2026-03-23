"""Workflow CRUD + execution API."""
import asyncio
import time
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, async_session
from app.models.workflow import Workflow
from app.models.agent import Agent
from app.models.agent_run import AgentRun
from app.schemas.workflow import WorkflowCreate, WorkflowUpdate, WorkflowResponse
from app.api.runs import _execute_run

logger = structlog.get_logger("workflows")

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


@router.get("")
async def list_workflows(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Workflow).order_by(Workflow.created_at.desc()))
    workflows = result.scalars().all()
    return {"items": [WorkflowResponse.from_orm_model(w) for w in workflows]}


@router.get("/{workflow_id}")
async def get_workflow(workflow_id: UUID, db: AsyncSession = Depends(get_db)):
    workflow = await db.get(Workflow, workflow_id)
    if not workflow:
        raise HTTPException(404, "Workflow not found")
    return WorkflowResponse.from_orm_model(workflow)


@router.post("", status_code=201)
async def create_workflow(body: WorkflowCreate, db: AsyncSession = Depends(get_db)):
    # Validate all agent_ids exist
    for step in body.steps:
        agent = await db.get(Agent, UUID(step.agent_id))
        if not agent:
            raise HTTPException(400, f"Agent {step.agent_id} not found")
        step.agent_name = agent.name

    workflow = Workflow(
        name=body.name,
        description=body.description,
        steps=[s.model_dump() for s in body.steps],
    )
    db.add(workflow)
    await db.commit()
    await db.refresh(workflow)
    return WorkflowResponse.from_orm_model(workflow)


@router.put("/{workflow_id}")
async def update_workflow(workflow_id: UUID, body: WorkflowUpdate, db: AsyncSession = Depends(get_db)):
    workflow = await db.get(Workflow, workflow_id)
    if not workflow:
        raise HTTPException(404, "Workflow not found")

    if body.name is not None:
        workflow.name = body.name
    if body.description is not None:
        workflow.description = body.description
    if body.enabled is not None:
        workflow.enabled = body.enabled
    if body.steps is not None:
        for step in body.steps:
            agent = await db.get(Agent, UUID(step.agent_id))
            if not agent:
                raise HTTPException(400, f"Agent {step.agent_id} not found")
            step.agent_name = agent.name
        workflow.steps = [s.model_dump() for s in body.steps]

    await db.commit()
    await db.refresh(workflow)
    return WorkflowResponse.from_orm_model(workflow)


@router.delete("/{workflow_id}", status_code=204)
async def delete_workflow(workflow_id: UUID, db: AsyncSession = Depends(get_db)):
    workflow = await db.get(Workflow, workflow_id)
    if not workflow:
        raise HTTPException(404, "Workflow not found")
    await db.delete(workflow)
    await db.commit()


@router.post("/{workflow_id}/run")
async def run_workflow(workflow_id: UUID, db: AsyncSession = Depends(get_db)):
    """Execute a workflow — runs each step sequentially, passing output forward."""
    workflow = await db.get(Workflow, workflow_id)
    if not workflow:
        raise HTTPException(404, "Workflow not found")
    if not workflow.enabled:
        raise HTTPException(400, "Workflow is disabled")
    if not workflow.steps:
        raise HTTPException(400, "Workflow has no steps")

    # Fire the workflow execution in the background
    asyncio.create_task(_execute_workflow(str(workflow.id)))

    return {"status": "started", "workflow_id": str(workflow.id), "steps": len(workflow.steps)}


async def _execute_workflow(workflow_id: str) -> None:
    """Execute a workflow sequentially — each step's output feeds the next."""
    async with async_session() as db:
        workflow = await db.get(Workflow, UUID(workflow_id))
        if not workflow:
            return

    await logger.ainfo("workflow_started", workflow=workflow.name, steps=len(workflow.steps))
    previous_output = ""

    for i, step in enumerate(workflow.steps):
        agent_id = step["agent_id"]
        instructions = step.get("instructions", "")
        pass_output = step.get("pass_output", True)

        # Prepend previous step's output if enabled
        if pass_output and previous_output and i > 0:
            instructions = f"{instructions}\n\nPrevious step output:\n{previous_output}"

        # Create a run for this step
        async with async_session() as db:
            run = AgentRun(agent_id=UUID(agent_id), instructions=instructions, status="pending")
            db.add(run)
            await db.commit()
            await db.refresh(run)
            run_id = str(run.id)

        await logger.ainfo("workflow_step", workflow=workflow.name, step=i + 1, agent=step.get("agent_name", "?"))

        # Execute and wait for completion
        await _execute_run(run_id, agent_id)

        # Read the result
        async with async_session() as db:
            run = await db.get(AgentRun, UUID(run_id))
            if not run or run.status == "failed":
                error = run.error if run else "Run not found"
                await logger.aerror("workflow_step_failed", workflow=workflow.name, step=i + 1, error=error)
                return  # abort workflow on failure

            previous_output = run.result or ""

    await logger.ainfo("workflow_completed", workflow=workflow.name)
