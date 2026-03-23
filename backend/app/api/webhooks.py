"""Webhook CRUD + trigger endpoint."""
import asyncio
import json
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.dependencies import get_db
from app.models.webhook import Webhook
from app.models.agent import Agent
from app.models.agent_run import AgentRun
from app.schemas.webhook import WebhookCreate, WebhookUpdate, WebhookResponse

logger = structlog.get_logger("webhooks")

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.get("")
async def list_webhooks(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Webhook).options(selectinload(Webhook.agent)).order_by(Webhook.created_at.desc())
    )
    webhooks = result.scalars().all()
    return {"items": [WebhookResponse.from_orm_model(w) for w in webhooks]}


@router.get("/{webhook_id}", response_model=WebhookResponse)
async def get_webhook(webhook_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Webhook).options(selectinload(Webhook.agent)).where(Webhook.id == webhook_id)
    )
    webhook = result.scalar_one_or_none()
    if not webhook:
        raise HTTPException(404, "Webhook not found")
    return WebhookResponse.from_orm_model(webhook)


@router.post("", status_code=201)
async def create_webhook(body: WebhookCreate, db: AsyncSession = Depends(get_db)):
    agent = await db.get(Agent, body.agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")

    webhook = Webhook(
        agent_id=body.agent_id,
        name=body.name,
        instructions_template=body.instructions_template,
        enabled=body.enabled,
    )
    db.add(webhook)
    await db.commit()
    await db.refresh(webhook, ["agent"])
    return WebhookResponse.from_orm_model(webhook)


@router.put("/{webhook_id}")
async def update_webhook(webhook_id: UUID, body: WebhookUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Webhook).options(selectinload(Webhook.agent)).where(Webhook.id == webhook_id)
    )
    webhook = result.scalar_one_or_none()
    if not webhook:
        raise HTTPException(404, "Webhook not found")

    if body.name is not None:
        webhook.name = body.name
    if body.instructions_template is not None:
        webhook.instructions_template = body.instructions_template
    if body.enabled is not None:
        webhook.enabled = body.enabled

    await db.commit()
    await db.refresh(webhook, ["agent"])
    return WebhookResponse.from_orm_model(webhook)


@router.delete("/{webhook_id}", status_code=204)
async def delete_webhook(webhook_id: UUID, db: AsyncSession = Depends(get_db)):
    webhook = await db.get(Webhook, webhook_id)
    if not webhook:
        raise HTTPException(404, "Webhook not found")
    await db.delete(webhook)
    await db.commit()


@router.post("/{token}/trigger")
async def trigger_webhook(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    """External trigger endpoint — called by third-party services."""
    result = await db.execute(
        select(Webhook).options(selectinload(Webhook.agent)).where(Webhook.token == token)
    )
    webhook = result.scalar_one_or_none()
    if not webhook:
        raise HTTPException(404, "Invalid webhook")
    if not webhook.enabled:
        raise HTTPException(403, "Webhook is disabled")

    # Parse request body
    try:
        body = await request.json()
    except Exception:
        body = {}

    # Build instructions from template + payload
    payload_str = json.dumps(body, indent=2)[:5000]
    if webhook.instructions_template:
        instructions = f"{webhook.instructions_template}\n\nWebhook payload:\n```json\n{payload_str}\n```"
    else:
        instructions = f"Process this webhook payload:\n```json\n{payload_str}\n```"

    # Create and fire agent run
    run = AgentRun(
        agent_id=webhook.agent_id,
        instructions=instructions,
        status="pending",
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    from app.api.runs import _execute_run
    asyncio.create_task(_execute_run(str(run.id), str(webhook.agent_id)))

    await logger.ainfo("webhook_triggered", webhook=webhook.name, agent=webhook.agent.name, run_id=str(run.id))

    return {"status": "triggered", "run_id": str(run.id)}
