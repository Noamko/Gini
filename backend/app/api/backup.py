"""Backup and restore API — exports/imports all config and history as portable JSON."""
from datetime import UTC, datetime
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.dependencies import get_db
from app.models.agent import Agent
from app.models.agent_run import AgentRun
from app.models.conversation import Conversation
from app.models.credential import Credential, skill_credentials
from app.models.event import Event
from app.models.execution_log import ExecutionLog
from app.models.message import Message
from app.models.schedule import Schedule
from app.models.skill import Skill, agent_skills, skill_tools
from app.models.tool import Tool
from app.models.webhook import Webhook
from app.models.workflow import Workflow

logger = structlog.get_logger("backup")

router = APIRouter(prefix="/api/backup", tags=["backup"])

BACKUP_VERSION = "1.1"


def _serialize_uuid(val):
    """Convert UUID to string for JSON serialization."""
    if isinstance(val, UUID):
        return str(val)
    return val


@router.get("/export")
async def export_backup(db: AsyncSession = Depends(get_db)):
    """Export all config and history data as portable JSON."""

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
            "code": t.code,
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

    # --- History data ---

    # Conversations (agent_name instead of agent_id)
    result = await db.execute(select(Conversation).order_by(Conversation.created_at))
    conversations = [
        {
            "id": str(c.id),
            "title": c.title,
            "agent_name": id_to_agent.get(c.agent_id) if c.agent_id else None,
            "metadata": c.metadata_,
            "created_at": c.created_at.isoformat(),
            "updated_at": c.updated_at.isoformat(),
        }
        for c in result.scalars().all()
    ]

    # Messages (conversation_id kept as-is since conversations have their IDs)
    result = await db.execute(select(Message).order_by(Message.created_at))
    messages = [
        {
            "id": str(m.id),
            "conversation_id": str(m.conversation_id),
            "role": m.role,
            "content": m.content,
            "tool_calls": m.tool_calls,
            "tool_call_id": m.tool_call_id,
            "token_count": m.token_count,
            "model_used": m.model_used,
            "cost_usd": float(m.cost_usd) if m.cost_usd else None,
            "metadata": m.metadata_,
            "created_at": m.created_at.isoformat(),
        }
        for m in result.scalars().all()
    ]

    # Agent runs (agent_name instead of agent_id)
    result = await db.execute(select(AgentRun).order_by(AgentRun.created_at))
    agent_runs = [
        {
            "id": str(r.id),
            "agent_name": id_to_agent.get(r.agent_id, "?"),
            "status": r.status,
            "instructions": r.instructions,
            "result": r.result,
            "error": r.error,
            "input_tokens": r.input_tokens,
            "output_tokens": r.output_tokens,
            "cost_usd": r.cost_usd,
            "duration_ms": r.duration_ms,
            "steps": r.steps,
            "created_at": r.created_at.isoformat(),
            "updated_at": r.updated_at.isoformat(),
        }
        for r in result.scalars().all()
    ]

    # Execution logs
    result = await db.execute(select(ExecutionLog).order_by(ExecutionLog.created_at))
    execution_logs = [
        {
            "id": str(el.id),
            "trace_id": el.trace_id,
            "conversation_id": str(el.conversation_id) if el.conversation_id else None,
            "agent_id": str(el.agent_id) if el.agent_id else None,
            "agent_name": el.agent_name,
            "step_type": el.step_type,
            "step_name": el.step_name,
            "step_order": el.step_order,
            "input_data": el.input_data,
            "output_data": el.output_data,
            "error": el.error,
            "duration_ms": el.duration_ms,
            "input_tokens": el.input_tokens,
            "output_tokens": el.output_tokens,
            "cost_usd": el.cost_usd,
            "model": el.model,
            "metadata": el.metadata_,
            "created_at": el.created_at.isoformat(),
        }
        for el in result.scalars().all()
    ]

    # Events
    result = await db.execute(select(Event).order_by(Event.created_at))
    events = [
        {
            "id": str(e.id),
            "event_type": e.event_type,
            "correlation_id": e.correlation_id,
            "conversation_id": str(e.conversation_id) if e.conversation_id else None,
            "source": e.source,
            "payload": e.payload,
            "status": e.status,
            "result": e.result,
            "created_at": e.created_at.isoformat(),
        }
        for e in result.scalars().all()
    ]

    await logger.ainfo(
        "backup_exported",
        agents=len(agents), skills=len(skills), credentials=len(credentials),
        conversations=len(conversations), messages=len(messages),
        agent_runs=len(agent_runs), execution_logs=len(execution_logs), events=len(events),
    )

    return {
        "version": BACKUP_VERSION,
        "exported_at": datetime.now(UTC).isoformat(),
        # Config
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
        # History
        "conversations": conversations,
        "messages": messages,
        "agent_runs": agent_runs,
        "execution_logs": execution_logs,
        "events": events,
    }


@router.post("/restore")
async def restore_backup(data: dict, db: AsyncSession = Depends(get_db)):
    """Restore config and history from a backup JSON. Upserts by name for config, by ID for history."""

    version = data.get("version", "")
    if version not in (BACKUP_VERSION, "1.0"):
        raise HTTPException(400, f"Unsupported backup version: {version}")

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

    await db.flush()

    # --- History data (upsert by ID) ---

    # 11. Conversations
    for c in data.get("conversations", []):
        cid = UUID(c["id"])
        existing = await db.get(Conversation, cid)
        if not existing:
            agent_id = agent_lookup.get(c.get("agent_name")) if c.get("agent_name") else None
            db.add(Conversation(
                id=cid, title=c.get("title"), agent_id=agent_id,
                metadata_=c.get("metadata", {}),
            ))
            counts["conversations"] = counts.get("conversations", 0) + 1
    await db.flush()

    # 12. Messages
    for m in data.get("messages", []):
        mid = UUID(m["id"])
        existing = await db.get(Message, mid)
        if not existing:
            db.add(Message(
                id=mid, conversation_id=UUID(m["conversation_id"]), role=m["role"],
                content=m.get("content"), tool_calls=m.get("tool_calls"),
                tool_call_id=m.get("tool_call_id"), token_count=m.get("token_count"),
                model_used=m.get("model_used"), cost_usd=m.get("cost_usd"),
                metadata_=m.get("metadata", {}),
            ))
            counts["messages"] = counts.get("messages", 0) + 1
    await db.flush()

    # 13. Agent runs
    for r in data.get("agent_runs", []):
        rid = UUID(r["id"])
        existing = await db.get(AgentRun, rid)
        if not existing:
            agent_id = agent_lookup.get(r.get("agent_name"))
            if agent_id:
                db.add(AgentRun(
                    id=rid, agent_id=agent_id, status=r["status"],
                    instructions=r.get("instructions"), result=r.get("result"),
                    error=r.get("error"), input_tokens=r.get("input_tokens", 0),
                    output_tokens=r.get("output_tokens", 0), cost_usd=r.get("cost_usd", 0),
                    duration_ms=r.get("duration_ms", 0), steps=r.get("steps", []),
                ))
                counts["agent_runs"] = counts.get("agent_runs", 0) + 1
    await db.flush()

    # 14. Execution logs
    for el in data.get("execution_logs", []):
        elid = UUID(el["id"])
        existing = await db.get(ExecutionLog, elid)
        if not existing:
            db.add(ExecutionLog(
                id=elid, trace_id=el["trace_id"],
                conversation_id=UUID(el["conversation_id"]) if el.get("conversation_id") else None,
                agent_id=UUID(el["agent_id"]) if el.get("agent_id") else None,
                agent_name=el.get("agent_name"), step_type=el["step_type"],
                step_name=el.get("step_name"), step_order=el.get("step_order", 0),
                input_data=el.get("input_data"), output_data=el.get("output_data"),
                error=el.get("error"), duration_ms=el.get("duration_ms", 0),
                input_tokens=el.get("input_tokens", 0), output_tokens=el.get("output_tokens", 0),
                cost_usd=el.get("cost_usd", 0), model=el.get("model"),
                metadata_=el.get("metadata", {}),
            ))
            counts["execution_logs"] = counts.get("execution_logs", 0) + 1
    await db.flush()

    # 15. Events
    for e in data.get("events", []):
        eid = UUID(e["id"])
        existing = await db.get(Event, eid)
        if not existing:
            db.add(Event(
                id=eid, event_type=e["event_type"],
                correlation_id=e.get("correlation_id"),
                conversation_id=UUID(e["conversation_id"]) if e.get("conversation_id") else None,
                source=e.get("source"), payload=e.get("payload"),
                status=e.get("status", "created"), result=e.get("result"),
            ))
            counts["events"] = counts.get("events", 0) + 1

    await db.commit()
    await logger.ainfo("backup_restored", counts=counts)

    return {"status": "restored", "counts": counts}
