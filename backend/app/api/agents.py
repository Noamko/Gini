from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.agent import Agent
from app.models.credential import Credential
from app.models.grant import agent_credentials, agent_tools
from app.models.skill import Skill, agent_skills
from app.schemas.agent import AgentCreate, AgentResponse, AgentUpdate, ToolGrant
from app.schemas.credential import CredentialResponse
from app.schemas.skill import SkillResponse
from app.services.skill_executor import invalidate_prompt_cache

router = APIRouter(prefix="/api/agents", tags=["agents"])


def _binding_ids(value) -> list[str]:
    """Normalize a slot binding (single id or list of ids) to a list of str ids."""
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)] if value else []


def _validate_bound_credentials(tool_grants: list[ToolGrant], credential_ids) -> None:
    """Ensure every slot binding references a credential the agent is granted."""
    granted = {str(c) for c in (credential_ids or [])}
    for grant in tool_grants or []:
        for slot, value in grant.slot_bindings.items():
            for cred_id in _binding_ids(value):
                if cred_id not in granted:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Tool '{grant.tool_name}' slot '{slot}' is bound to a credential "
                            "the agent isn't granted. Grant the credential first."
                        ),
                    )


async def _existing_credential_ids(db: AsyncSession, agent_id: UUID) -> list[UUID]:
    result = await db.execute(select(agent_credentials.c.credential_id).where(agent_credentials.c.agent_id == agent_id))
    return [row[0] for row in result.all()]


async def _set_agent_skills(db: AsyncSession, agent_id: UUID, skill_ids) -> None:
    await db.execute(delete(agent_skills).where(agent_skills.c.agent_id == agent_id))
    for skill_id in skill_ids:
        await db.execute(agent_skills.insert().values(agent_id=agent_id, skill_id=skill_id))


async def _set_agent_credentials(db: AsyncSession, agent_id: UUID, credential_ids) -> None:
    await db.execute(delete(agent_credentials).where(agent_credentials.c.agent_id == agent_id))
    for credential_id in credential_ids:
        await db.execute(agent_credentials.insert().values(agent_id=agent_id, credential_id=credential_id))


async def _set_agent_tool_grants(db: AsyncSession, agent_id: UUID, tool_grants: list[ToolGrant]) -> None:
    await db.execute(delete(agent_tools).where(agent_tools.c.agent_id == agent_id))
    for grant in tool_grants:
        await db.execute(
            agent_tools.insert().values(
                agent_id=agent_id,
                tool_name=grant.tool_name,
                slot_bindings={
                    slot: (ids if isinstance(value, list) else ids[0])
                    for slot, value in grant.slot_bindings.items()
                    if (ids := _binding_ids(value))
                },
            )
        )


@router.get("")
async def list_agents(offset: int = 0, limit: int = 50, db: AsyncSession = Depends(get_db)):
    count_result = await db.execute(select(func.count(Agent.id)))
    total = count_result.scalar_one()

    result = await db.execute(
        select(Agent).order_by(Agent.is_main.desc(), Agent.created_at.desc()).offset(offset).limit(limit)
    )
    agents = result.scalars().all()
    return {
        "items": [AgentResponse.from_orm_model(a) for a in agents],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.post("", status_code=201)
async def create_agent(body: AgentCreate, db: AsyncSession = Depends(get_db)):
    _validate_bound_credentials(body.tool_grants, body.credential_ids)
    agent = Agent(
        name=body.name,
        description=body.description,
        system_prompt=body.system_prompt,
        llm_provider=body.llm_provider,
        llm_model=body.llm_model,
        temperature=body.temperature,
        max_tokens=body.max_tokens,
        is_main=body.is_main,
        auto_approve=body.auto_approve,
        daily_budget_usd=body.daily_budget_usd,
        metadata_=body.metadata,
    )
    db.add(agent)
    await db.flush()
    await _set_agent_skills(db, agent.id, body.skill_ids)
    await _set_agent_credentials(db, agent.id, body.credential_ids)
    await _set_agent_tool_grants(db, agent.id, body.tool_grants)
    await db.commit()
    await db.refresh(agent)
    return AgentResponse.from_orm_model(agent)


@router.get("/{agent_id}")
async def get_agent(agent_id: UUID, db: AsyncSession = Depends(get_db)):
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return AgentResponse.from_orm_model(agent)


@router.put("/{agent_id}")
async def update_agent(agent_id: UUID, body: AgentUpdate, db: AsyncSession = Depends(get_db)):
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    update_data = body.model_dump(exclude_unset=True)
    # Grant fields are synced against junction/grant tables, not set as columns.
    for grant_field in ("tool_grants", "credential_ids", "skill_ids"):
        update_data.pop(grant_field, None)
    if "metadata" in update_data:
        update_data["metadata_"] = update_data.pop("metadata")

    for key, value in update_data.items():
        setattr(agent, key, value)

    if body.skill_ids is not None:
        await _set_agent_skills(db, agent_id, body.skill_ids)
    if body.credential_ids is not None:
        await _set_agent_credentials(db, agent_id, body.credential_ids)
    if body.tool_grants is not None:
        effective_credentials = (
            body.credential_ids if body.credential_ids is not None else await _existing_credential_ids(db, agent_id)
        )
        _validate_bound_credentials(body.tool_grants, effective_credentials)
        await _set_agent_tool_grants(db, agent_id, body.tool_grants)

    await db.commit()
    await db.refresh(agent)
    await invalidate_prompt_cache(agent_id)
    return AgentResponse.from_orm_model(agent)


@router.get("/{agent_id}/skills", response_model=list[SkillResponse])
async def get_agent_skills(agent_id: UUID, db: AsyncSession = Depends(get_db)):
    """Get all skills assigned to an agent."""
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    result = await db.execute(
        select(Skill)
        .join(agent_skills, Skill.id == agent_skills.c.skill_id)
        .where(agent_skills.c.agent_id == agent_id)
        .order_by(Skill.name)
    )
    return result.scalars().all()


@router.get("/{agent_id}/tools")
async def get_agent_tools(agent_id: UUID, db: AsyncSession = Depends(get_db)):
    """Get the agent's direct tool grants with their credential slot bindings."""
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    result = await db.execute(
        select(agent_tools.c.tool_name, agent_tools.c.slot_bindings)
        .where(agent_tools.c.agent_id == agent_id)
        .order_by(agent_tools.c.tool_name)
    )
    return [{"tool_name": tool_name, "slot_bindings": slot_bindings or {}} for tool_name, slot_bindings in result.all()]


@router.get("/{agent_id}/credentials", response_model=list[CredentialResponse])
async def list_agent_credentials(agent_id: UUID, db: AsyncSession = Depends(get_db)):
    """Get the credentials granted directly to an agent."""
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    result = await db.execute(
        select(Credential)
        .join(agent_credentials, Credential.id == agent_credentials.c.credential_id)
        .where(agent_credentials.c.agent_id == agent_id)
        .order_by(Credential.name)
    )
    return result.scalars().all()


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(agent_id: UUID, db: AsyncSession = Depends(get_db)):
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.is_main:
        raise HTTPException(status_code=400, detail="Cannot delete the main agent")
    await db.delete(agent)
    await db.commit()
