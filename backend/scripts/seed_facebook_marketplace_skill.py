"""Seed the "Facebook Marketplace" skill and grant it to the main agent.

The skill bundles the read-only Marketplace tools — facebook_marketplace_search and
facebook_marketplace_listing — which are opt-in (hidden from the default catalog). It also
bundles the ``facebook_session`` credential if one exists so the tools' session slot auto-binds.

Create the credential first (Settings → Credentials, or the credentials API) with:
    name: facebook_session   type: facebook_session
    value: the c_user/xs cookies from a logged-in facebook.com browser

Run AFTER seed_tools.py (the tool rows must exist first). Idempotent: safe to re-run.
"""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models.agent import Agent
from app.models.credential import Credential
from app.models.skill import Skill, agent_skills
from app.models.tool import Tool
from app.services.skill_executor import invalidate_prompt_cache

SKILL_NAME = "Facebook Marketplace"
SKILL_DESCRIPTION = (
    "Search and read Facebook Marketplace listings and Facebook group posts using the operator's "
    "Facebook session. Read-only: it never posts, messages, or changes account state."
)
SKILL_INSTRUCTIONS = (
    "You can browse Facebook Marketplace and the Facebook groups the operator's account has joined. "
    "Use facebook_marketplace_search to find listings by keyword (optionally filtering by location, "
    "price, recency, and sort order), and facebook_marketplace_listing to fetch the full detail of a "
    "single item by id or URL. For groups: facebook_group_list enumerates the account's joined groups "
    "(filter by a name keyword, e.g. 'tel aviv' or a Hebrew term) and facebook_group_posts fetches the "
    "newest posts from up to 10 groups per call — scan groups in batches, then judge relevance from the "
    "post text yourself (group posts are free-form; prices, room counts, and neighborhoods appear in "
    "the text, often in Hebrew). These tools require a valid Facebook session credential; if a call "
    "reports a login wall, tell the user their facebook_session cookies need refreshing. Never attempt "
    "to post, comment, or message — these tools are read-only."
)
TOOL_NAMES = [
    "facebook_marketplace_search",
    "facebook_marketplace_listing",
    "facebook_group_list",
    "facebook_group_posts",
]
CREDENTIAL_NAME = "facebook_session"


async def seed():
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        # Load the tool rows (seeded by seed_tools.py / app startup).
        result = await session.execute(select(Tool).where(Tool.name.in_(TOOL_NAMES)))
        tools = list(result.scalars().all())
        found = {t.name for t in tools}
        missing = set(TOOL_NAMES) - found
        if missing:
            print(f"WARNING: tool rows not found yet: {sorted(missing)}. Run seed_tools first.")
        if not tools:
            print("No Marketplace tool rows present — aborting skill seed.")
            await engine.dispose()
            return

        # Bundle the session credential if the operator has created it.
        cred_result = await session.execute(select(Credential).where(Credential.name == CREDENTIAL_NAME))
        credential = cred_result.scalar_one_or_none()
        if credential is None:
            print(
                f"NOTE: no '{CREDENTIAL_NAME}' credential yet — the skill is seeded without it. "
                "Create the credential and re-run this script to auto-bind the session."
            )

        # Upsert the skill and (re)link its tools + credential.
        result = await session.execute(select(Skill).where(Skill.name == SKILL_NAME))
        skill = result.scalar_one_or_none()
        if skill:
            skill.description = SKILL_DESCRIPTION
            skill.instructions = SKILL_INSTRUCTIONS
            skill.is_active = True
            skill.tools = tools
            skill.credentials = [credential] if credential else []
            print(f"Updated skill: {SKILL_NAME}")
        else:
            skill = Skill(
                name=SKILL_NAME,
                description=SKILL_DESCRIPTION,
                instructions=SKILL_INSTRUCTIONS,
                is_active=True,
            )
            skill.tools = tools
            skill.credentials = [credential] if credential else []
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
