"""Seed the "Agent Management" skill and grant it to the main agent.

The skill bundles the agent-management ("meta") tools — create_agent, list_agents, create_workflow,
create_webhook, create_tool — which are opt-in (hidden from the default catalog). Assigning this skill
is how an agent is granted the ability to create agents/workflows/webhooks/tools.

Run AFTER seed_tools.py (the tool rows must exist first). Idempotent: safe to re-run.
"""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models.agent import Agent
from app.models.skill import Skill, agent_skills
from app.models.tool import Tool
from app.services.skill_executor import invalidate_prompt_cache

SKILL_NAME = "Agent Management"
SKILL_DESCRIPTION = (
    "Lets the agent create and manage other agents, workflows, webhooks, and custom tools. "
    "Powerful: create operations require human approval unless the agent has auto_approve."
)
SKILL_INSTRUCTIONS = (
    "You can extend the platform. Use list_agents to discover agent ids before referencing them. "
    "Use create_agent to spin up focused specialists, create_workflow to chain agents, create_webhook "
    "to expose an inbound trigger for an agent, and create_tool to author a new custom tool. "
    "Create operations require approval — explain what you intend to create before calling them."
)
META_TOOL_NAMES = ["create_agent", "list_agents", "create_workflow", "create_webhook", "create_tool"]


async def seed():
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        # Load the meta-tool rows (seeded by seed_tools.py / app startup).
        result = await session.execute(select(Tool).where(Tool.name.in_(META_TOOL_NAMES)))
        tools = list(result.scalars().all())
        found = {t.name for t in tools}
        missing = set(META_TOOL_NAMES) - found
        if missing:
            print(f"WARNING: meta-tool rows not found yet: {sorted(missing)}. Run seed_tools first.")
        if not tools:
            print("No meta-tool rows present — aborting skill seed.")
            await engine.dispose()
            return

        # Upsert the skill and (re)link its tools.
        result = await session.execute(select(Skill).where(Skill.name == SKILL_NAME))
        skill = result.scalar_one_or_none()
        if skill:
            skill.description = SKILL_DESCRIPTION
            skill.instructions = SKILL_INSTRUCTIONS
            skill.is_active = True
            skill.tools = tools
            print(f"Updated skill: {SKILL_NAME}")
        else:
            skill = Skill(
                name=SKILL_NAME,
                description=SKILL_DESCRIPTION,
                instructions=SKILL_INSTRUCTIONS,
                is_active=True,
            )
            skill.tools = tools
            session.add(skill)
            print(f"Created skill: {SKILL_NAME}")

        await session.commit()
        await session.refresh(skill)

        # Assign to the main agent (idempotent).
        result = await session.execute(select(Agent).where(Agent.is_main == True))  # noqa: E712
        main_agent = result.scalar_one_or_none()
        if not main_agent:
            print("No main agent found — skipping assignment. Run seed_main_agent first.")
            await engine.dispose()
            return

        existing = await session.execute(
            select(agent_skills.c.skill_id).where(
                (agent_skills.c.agent_id == main_agent.id) & (agent_skills.c.skill_id == skill.id)
            )
        )
        if existing.first() is None:
            await session.execute(agent_skills.insert().values(agent_id=main_agent.id, skill_id=skill.id))
            await session.commit()
            print(f"Assigned '{SKILL_NAME}' to main agent: {main_agent.name}")
        else:
            print(f"'{SKILL_NAME}' already assigned to main agent: {main_agent.name}")

        await invalidate_prompt_cache(main_agent.id)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
