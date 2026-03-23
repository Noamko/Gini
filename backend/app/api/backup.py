"""Backup and restore API — exports/imports all config as portable JSON."""
from datetime import datetime, timezone
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.dependencies import get_db
from app.models.agent import Agent
from app.models.tool import Tool
from app.models.credential import Credential
from app.models.skill import Skill, agent_skills, skill_tools
from app.models.credential import skill_credentials
from app.models.workflow import Workflow
from app.models.schedule import Schedule
from app.models.webhook import Webhook

logger = structlog.get_logger("backup")

router = APIRouter(prefix="/api/backup", tags=["backup"])

BACKUP_VERSION = "1.0"


@router.get("/export")
async def export_backup(db: AsyncSession = Depends(get_db)):
    """Export all config data as portable JSON."""

    # Agents
    result = await db.execute(select(Agent).order_by(Agent.name))
    agents = [
        {
            "name": a.name,
            "description": a.description,
            "system_prompt": a.system_prompt,
            "llm_provider": a.llm_provider,
            "llm_model": a.llm_model,
            "temperature": a.temperature,
            "max_tokens": a.max_tokens,
            "is_main": a.is_main,
            "is_active": a.is_active,
            "use_memory": a.use_memory,
            "auto_approve": a.auto_approve,
            "daily_budget_usd": a.daily_budget_usd,
            "metadata": a.metadata_,
        }
        for a in result.scalars().all()
    ]

    # Tools
    result = await db.execute(select(Tool).order_by(Tool.name))
    tools = [
        {
            "name": t.name,
            "description": t.description,
            "parameters_schema": t.parameters_schema,
            "implementation": t.implementation,
            "requires_sandbox": t.requires_sandbox,
            "requires_approval": t.requires_approval,
            "is_builtin": t.is_builtin,
            "is_active": t.is_active,
        }
        for t in result.scalars().all()
    ]

    # Credentials (encrypted values exported as-is)
    result = await db.execute(select(Credential).order_by(Credential.name))
    credentials = [
        {
            "name": c.name,
            "description": c.description,
            "credential_type": c.credential_type,
            "encrypted_value": c.encrypted_value,
            "is_active": c.is_active,
        }
        for c in result.scalars().all()
    ]

    # Skills
    result = await db.execute(
        select(Skill).options(selectinload(Skill.tools), selectinload(Skill.credentials)).order_by(Skill.name)
    )
    skills = [
        {
            "name": s.name,
            "description": s.description,
            "instructions": s.instructions,
            "is_active": s.is_active,
            "metadata": s.metadata_,
        }
        for s in result.scalars().all()
    ]

    # Junction: agent_skills (by name)
    result = await db.execute(
        select(agent_skills.c.agent_id, agent_skills.c.skill_id)
    )
    agent_skill_rows = result.all()
    # Resolve IDs to names
    agent_map = {a["name"]: None for a in agents}  # just need names
    result = await db.execute(select(Agent.id, Agent.name))
    id_to_agent = {row[0]: row[1] for row in result.all()}
    result = await db.execute(select(Skill.id, Skill.name))
    id_to_skill = {row[0]: row[1] for row in result.all()}

    agent_skills_export = [
        {"agent_name": id_to_agent.get(row[0], "?"), "skill_name": id_to_skill.get(row[1], "?")}
        for row in agent_skill_rows
    ]

    # Junction: skill_tools (by name)
    result = await db.execute(select(skill_tools.c.skill_id, skill_tools.c.tool_id))
    st_rows = result.all()
    result = await db.execute(select(Tool.id, Tool.name))
    id_to_tool = {row[0]: row[1] for row in result.all()}

    skill_tools_export = [
        {"skill_name": id_to_skill.get(row[0], "?"), "tool_name": id_to_tool.get(row[1], "?")}
        for row in st_rows
    ]

    # Junction: skill_credentials (by name)
    result = await db.execute(select(skill_credentials.c.skill_id, skill_credentials.c.credential_id))
    sc_rows = result.all()
    result = await db.execute(select(Credential.id, Credential.name))
    id_to_cred = {row[0]: row[1] for row in result.all()}

    skill_credentials_export = [
        {"skill_name": id_to_skill.get(row[0], "?"), "credential_name": id_to_cred.get(row[1], "?")}
        for row in sc_rows
    ]

    # Workflows (replace agent_ids with names in steps)
    result = await db.execute(select(Workflow).order_by(Workflow.name))
    workflows = []
    for w in result.scalars().all():
        steps = []
        for s in (w.steps or []):
            step = dict(s)
            aid = step.get("agent_id")
            if aid:
                step["agent_name"] = id_to_agent.get(UUID(aid) if isinstance(aid, str) else aid, step.get("agent_name", "?"))
            step.pop("agent_id", None)
            steps.append(step)
        workflows.append({
            "name": w.name,
            "description": w.description,
            "enabled": w.enabled,
            "steps": steps,
        })

    # Schedules (agent_name instead of agent_id)
    result = await db.execute(select(Schedule).options(selectinload(Schedule.agent)).order_by(Schedule.name))
    schedules = [
        {
            "name": s.name,
            "agent_name": s.agent.name if s.agent else "?",
            "cron_expression": s.cron_expression,
            "instructions": s.instructions,
            "enabled": s.enabled,
        }
        for s in result.scalars().all()
    ]

    # Webhooks (agent_name instead of agent_id)
    result = await db.execute(select(Webhook).options(selectinload(Webhook.agent)).order_by(Webhook.name))
    webhooks = [
        {
            "name": w.name,
            "agent_name": w.agent.name if w.agent else "?",
            "token": w.token,
            "instructions_template": w.instructions_template,
            "enabled": w.enabled,
        }
        for w in result.scalars().all()
    ]

    await logger.ainfo("backup_exported", agents=len(agents), skills=len(skills), credentials=len(credentials))

    return {
        "version": BACKUP_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "agents": agents,
        "tools": tools,
        "credentials": credentials,
        "skills": skills,
        "agent_skills": agent_skills_export,
        "skill_tools": skill_tools_export,
        "skill_credentials": skill_credentials_export,
        "workflows": workflows,
        "schedules": schedules,
        "webhooks": webhooks,
    }


@router.post("/restore")
async def restore_backup(data: dict, db: AsyncSession = Depends(get_db)):
    """Restore config from a backup JSON. Upserts by name."""

    if data.get("version") != BACKUP_VERSION:
        raise HTTPException(400, f"Unsupported backup version: {data.get('version')}")

    counts = {}

    # 1. Tools
    for t in data.get("tools", []):
        existing = (await db.execute(select(Tool).where(Tool.name == t["name"]))).scalar_one_or_none()
        if existing:
            for k, v in t.items():
                if k != "name":
                    setattr(existing, k, v)
        else:
            db.add(Tool(**t))
        counts["tools"] = counts.get("tools", 0) + 1
    await db.flush()

    # 2. Credentials
    for c in data.get("credentials", []):
        existing = (await db.execute(select(Credential).where(Credential.name == c["name"]))).scalar_one_or_none()
        if existing:
            for k, v in c.items():
                if k != "name":
                    setattr(existing, k, v)
        else:
            db.add(Credential(**c))
        counts["credentials"] = counts.get("credentials", 0) + 1
    await db.flush()

    # 3. Agents
    for a in data.get("agents", []):
        existing = (await db.execute(select(Agent).where(Agent.name == a["name"]))).scalar_one_or_none()
        if existing:
            for k, v in a.items():
                if k == "metadata":
                    existing.metadata_ = v
                elif k != "name":
                    setattr(existing, k, v)
        else:
            agent_data = dict(a)
            if "metadata" in agent_data:
                agent_data["metadata_"] = agent_data.pop("metadata")
            db.add(Agent(**agent_data))
        counts["agents"] = counts.get("agents", 0) + 1
    await db.flush()

    # 4. Skills
    for s in data.get("skills", []):
        existing = (await db.execute(select(Skill).where(Skill.name == s["name"]))).scalar_one_or_none()
        if existing:
            for k, v in s.items():
                if k == "metadata":
                    existing.metadata_ = v
                elif k != "name":
                    setattr(existing, k, v)
        else:
            skill_data = dict(s)
            if "metadata" in skill_data:
                skill_data["metadata_"] = skill_data.pop("metadata")
            db.add(Skill(**skill_data))
        counts["skills"] = counts.get("skills", 0) + 1
    await db.flush()

    # Build name→id lookups
    agent_lookup = {r[0]: r[1] for r in (await db.execute(select(Agent.name, Agent.id))).all()}
    skill_lookup = {r[0]: r[1] for r in (await db.execute(select(Skill.name, Skill.id))).all()}
    tool_lookup = {r[0]: r[1] for r in (await db.execute(select(Tool.name, Tool.id))).all()}
    cred_lookup = {r[0]: r[1] for r in (await db.execute(select(Credential.name, Credential.id))).all()}

    # 5. agent_skills
    for link in data.get("agent_skills", []):
        aid = agent_lookup.get(link["agent_name"])
        sid = skill_lookup.get(link["skill_name"])
        if aid and sid:
            await db.execute(
                text("INSERT INTO agent_skills (agent_id, skill_id) VALUES (:a, :s) ON CONFLICT DO NOTHING"),
                {"a": aid, "s": sid},
            )
    counts["agent_skills"] = len(data.get("agent_skills", []))

    # 6. skill_tools
    for link in data.get("skill_tools", []):
        sid = skill_lookup.get(link["skill_name"])
        tid = tool_lookup.get(link["tool_name"])
        if sid and tid:
            await db.execute(
                text("INSERT INTO skill_tools (skill_id, tool_id) VALUES (:s, :t) ON CONFLICT DO NOTHING"),
                {"s": sid, "t": tid},
            )
    counts["skill_tools"] = len(data.get("skill_tools", []))

    # 7. skill_credentials
    for link in data.get("skill_credentials", []):
        sid = skill_lookup.get(link["skill_name"])
        cid = cred_lookup.get(link["credential_name"])
        if sid and cid:
            await db.execute(
                text("INSERT INTO skill_credentials (skill_id, credential_id) VALUES (:s, :c) ON CONFLICT DO NOTHING"),
                {"s": sid, "c": cid},
            )
    counts["skill_credentials"] = len(data.get("skill_credentials", []))

    # 8. Workflows (re-resolve agent names → IDs in steps)
    for w in data.get("workflows", []):
        steps = []
        for s in w.get("steps", []):
            step = dict(s)
            aname = step.pop("agent_name", None)
            if aname and aname in agent_lookup:
                step["agent_id"] = str(agent_lookup[aname])
                step["agent_name"] = aname
            steps.append(step)

        existing = (await db.execute(select(Workflow).where(Workflow.name == w["name"]))).scalar_one_or_none()
        if existing:
            existing.description = w.get("description")
            existing.enabled = w.get("enabled", True)
            existing.steps = steps
        else:
            db.add(Workflow(name=w["name"], description=w.get("description"), enabled=w.get("enabled", True), steps=steps))
        counts["workflows"] = counts.get("workflows", 0) + 1
    await db.flush()

    # 9. Schedules
    from app.services.scheduler import compute_next_run
    for s in data.get("schedules", []):
        aid = agent_lookup.get(s["agent_name"])
        if not aid:
            continue
        existing = (await db.execute(select(Schedule).where(Schedule.name == s["name"]))).scalar_one_or_none()
        next_run = compute_next_run(s["cron_expression"])
        if existing:
            existing.agent_id = aid
            existing.cron_expression = s["cron_expression"]
            existing.instructions = s.get("instructions")
            existing.enabled = s.get("enabled", True)
            existing.next_run_at = next_run
        else:
            db.add(Schedule(
                agent_id=aid, name=s["name"], cron_expression=s["cron_expression"],
                instructions=s.get("instructions"), enabled=s.get("enabled", True), next_run_at=next_run,
            ))
        counts["schedules"] = counts.get("schedules", 0) + 1

    # 10. Webhooks
    for w in data.get("webhooks", []):
        aid = agent_lookup.get(w["agent_name"])
        if not aid:
            continue
        existing = (await db.execute(select(Webhook).where(Webhook.name == w["name"]))).scalar_one_or_none()
        if existing:
            existing.agent_id = aid
            existing.instructions_template = w.get("instructions_template")
            existing.enabled = w.get("enabled", True)
        else:
            db.add(Webhook(
                agent_id=aid, name=w["name"], token=w.get("token", Webhook.token.default.arg()),
                instructions_template=w.get("instructions_template"), enabled=w.get("enabled", True),
            ))
        counts["webhooks"] = counts.get("webhooks", 0) + 1

    await db.commit()
    await logger.ainfo("backup_restored", counts=counts)

    return {"status": "restored", "counts": counts}
