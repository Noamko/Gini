"""Skill CRUD endpoints."""
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.skill import Skill, agent_skills, skill_tools
from app.models.tool import Tool
from app.models.credential import Credential
from app.schemas.skill import SkillCreate, SkillUpdate, SkillResponse
from app.services.skill_executor import invalidate_prompt_cache

logger = structlog.get_logger("skills_api")

router = APIRouter(prefix="/api/skills", tags=["skills"])


@router.get("", response_model=list[SkillResponse])
async def list_skills(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Skill).order_by(Skill.name))
    return result.scalars().all()


@router.get("/{skill_id}", response_model=SkillResponse)
async def get_skill(skill_id: UUID, db: AsyncSession = Depends(get_db)):
    skill = await db.get(Skill, skill_id)
    if not skill:
        raise HTTPException(404, "Skill not found")
    return skill


@router.post("", response_model=SkillResponse, status_code=201)
async def create_skill(body: SkillCreate, db: AsyncSession = Depends(get_db)):
    skill = Skill(
        name=body.name,
        description=body.description,
        instructions=body.instructions,
    )

    if body.tool_ids:
        result = await db.execute(select(Tool).where(Tool.id.in_(body.tool_ids)))
        skill.tools = list(result.scalars().all())

    if body.credential_ids:
        result = await db.execute(select(Credential).where(Credential.id.in_(body.credential_ids)))
        skill.credentials = list(result.scalars().all())

    db.add(skill)
    await db.commit()
    await db.refresh(skill)
    return skill


@router.put("/{skill_id}", response_model=SkillResponse)
async def update_skill(skill_id: UUID, body: SkillUpdate, db: AsyncSession = Depends(get_db)):
    skill = await db.get(Skill, skill_id)
    if not skill:
        raise HTTPException(404, "Skill not found")

    if body.name is not None:
        skill.name = body.name
    if body.description is not None:
        skill.description = body.description
    if body.instructions is not None:
        skill.instructions = body.instructions
    if body.is_active is not None:
        skill.is_active = body.is_active

    if body.tool_ids is not None:
        result = await db.execute(select(Tool).where(Tool.id.in_(body.tool_ids)))
        skill.tools = list(result.scalars().all())

    if body.credential_ids is not None:
        result = await db.execute(select(Credential).where(Credential.id.in_(body.credential_ids)))
        skill.credentials = list(result.scalars().all())

    await db.commit()
    await db.refresh(skill)

    # Invalidate prompt cache for all agents that use this skill
    result = await db.execute(
        select(agent_skills.c.agent_id).where(agent_skills.c.skill_id == skill_id)
    )
    for (agent_id,) in result:
        await invalidate_prompt_cache(agent_id)

    return skill


@router.delete("/{skill_id}", status_code=204)
async def delete_skill(skill_id: UUID, db: AsyncSession = Depends(get_db)):
    skill = await db.get(Skill, skill_id)
    if not skill:
        raise HTTPException(404, "Skill not found")

    # Invalidate prompt cache for affected agents before deleting
    result = await db.execute(
        select(agent_skills.c.agent_id).where(agent_skills.c.skill_id == skill_id)
    )
    for (agent_id,) in result:
        await invalidate_prompt_cache(agent_id)

    await db.delete(skill)
    await db.commit()


@router.post("/{skill_id}/assign/{agent_id}", status_code=200)
async def assign_skill_to_agent(skill_id: UUID, agent_id: UUID, db: AsyncSession = Depends(get_db)):
    """Assign a skill to an agent."""
    await db.execute(
        agent_skills.insert().values(agent_id=agent_id, skill_id=skill_id)
    )
    await db.commit()
    await invalidate_prompt_cache(agent_id)
    return {"status": "assigned"}


@router.delete("/{skill_id}/assign/{agent_id}", status_code=200)
async def unassign_skill_from_agent(skill_id: UUID, agent_id: UUID, db: AsyncSession = Depends(get_db)):
    """Remove a skill from an agent."""
    await db.execute(
        agent_skills.delete().where(
            (agent_skills.c.agent_id == agent_id) & (agent_skills.c.skill_id == skill_id)
        )
    )
    await db.commit()
    await invalidate_prompt_cache(agent_id)
    return {"status": "unassigned"}
