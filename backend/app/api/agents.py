from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.agent import Agent
from app.models.skill import Skill, agent_skills
from app.schemas.agent import AgentCreate, AgentResponse, AgentUpdate
from app.schemas.skill import SkillResponse

router = APIRouter(prefix="/api/agents", tags=["agents"])


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
    agent = Agent(
        name=body.name,
        description=body.description,
        system_prompt=body.system_prompt,
        llm_provider=body.llm_provider,
        llm_model=body.llm_model,
        temperature=body.temperature,
        max_tokens=body.max_tokens,
        is_main=body.is_main,
        metadata_=body.metadata,
    )
    db.add(agent)
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
    # Handle metadata field name mapping
    if "metadata" in update_data:
        update_data["metadata_"] = update_data.pop("metadata")

    for key, value in update_data.items():
        setattr(agent, key, value)

    await db.commit()
    await db.refresh(agent)
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


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(agent_id: UUID, db: AsyncSession = Depends(get_db)):
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.is_main:
        raise HTTPException(status_code=400, detail="Cannot delete the main agent")
    await db.delete(agent)
    await db.commit()
