"""Seed a dedicated "Marketplace Scout" agent and grant it the Facebook Marketplace skill.

A focused, non-main agent so Marketplace browsing runs off Gini. The skill bundles the two
read-only tools (facebook_marketplace_search, facebook_marketplace_listing) and the
facebook_session credential, which auto-binds to the tools' session slot.

Run AFTER seed_facebook_marketplace_skill.py (the skill must exist first). Idempotent.
"""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models.agent import Agent
from app.models.skill import Skill, agent_skills
from app.services.skill_executor import invalidate_prompt_cache

AGENT_NAME = "Marketplace Scout"
AGENT_DESCRIPTION = "Dedicated Facebook Marketplace browser — searches and reads listings on the user's behalf."
SKILL_NAME = "Facebook Marketplace"
AGENT_PROMPT = """\
You are Marketplace Scout, a focused assistant for browsing Facebook Marketplace.

Your job is to help the user find and evaluate listings. Use facebook_marketplace_search to find \
items by keyword — apply the location, price, recency, and sort filters that match what the user \
asked for. Use facebook_marketplace_listing to pull the full detail (description, all photos, price) \
of a specific item when the user wants a closer look or a comparison.

These tools are read-only: you can search and read, but you never post listings, message sellers, \
or change anything on the account. If a search omits a location, Facebook uses the account's default \
Marketplace area — pass an explicit location when the user names a city.

Present results clearly: lead with price and title, include the location and a link, and group or \
rank them the way the user cares about (cheapest, nearest, newest). If a call reports that the \
Facebook session hit a login wall, tell the user their facebook_session credential needs refreshing. \
Be concise and practical — you are a scout, not a salesperson.
"""


async def seed():
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        # Upsert the agent.
        result = await session.execute(select(Agent).where(Agent.name == AGENT_NAME))
        agent = result.scalar_one_or_none()
        if agent:
            agent.description = AGENT_DESCRIPTION
            agent.system_prompt = AGENT_PROMPT
            agent.is_active = True
            print(f"Updated agent: {AGENT_NAME} ({agent.id})")
        else:
            agent = Agent(
                name=AGENT_NAME,
                description=AGENT_DESCRIPTION,
                system_prompt=AGENT_PROMPT,
                llm_provider=settings.default_llm_provider,
                llm_model=settings.default_llm_model,
                temperature=settings.default_temperature,
                max_tokens=settings.default_max_tokens,
                is_main=False,
                state="idle",
            )
            session.add(agent)
            print(f"Created agent: {AGENT_NAME}")
        await session.commit()
        await session.refresh(agent)

        # Grant the Facebook Marketplace skill (idempotent).
        result = await session.execute(select(Skill).where(Skill.name == SKILL_NAME))
        skill = result.scalar_one_or_none()
        if not skill:
            print(f"Skill '{SKILL_NAME}' not found — run seed_facebook_marketplace_skill first.")
            await engine.dispose()
            return

        existing = await session.execute(
            select(agent_skills.c.skill_id).where(
                (agent_skills.c.agent_id == agent.id) & (agent_skills.c.skill_id == skill.id)
            )
        )
        if existing.first() is None:
            await session.execute(agent_skills.insert().values(agent_id=agent.id, skill_id=skill.id))
            await session.commit()
            print(f"Granted '{SKILL_NAME}' to {AGENT_NAME}")
        else:
            print(f"'{SKILL_NAME}' already granted to {AGENT_NAME}")

        await invalidate_prompt_cache(agent.id)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
