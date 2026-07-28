"""Seed the Haifa-region rental scan on Facebook Marketplace, delivered to Noam + Tom.

Replaces the broken Yad2 "Haifa real estate for tom" schedule (Yad2 now serves a Radware
bot-verification page to the scraper, and yad2_search never covered Nesher/Krayot). This scan
runs on a dedicated agent because ``chat_id`` slot bindings are per agent+tool, and the
existing Marketplace Scout broadcasts to Noam + Gili:
  1. Upserts a "Haifa Marketplace Scout" agent and grants it the Facebook Marketplace skill.
  2. Grants the three send_telegram tools with the ``chat_id`` slot bound to the Noam + Tom
     Telegram credentials (a send with no chat_id broadcasts to both), plus direct grants
     of those two credentials.
  3. Upserts a daily schedule ("Daily Haifa region Marketplace rental scan", 06:15 UTC —
     staggered after the 06:00 Tel Aviv scans so the Pi isn't running three browsers at once).
  4. Disables the superseded Yad2 schedule "Haifa real estate for tom" if present.

Run AFTER seed_facebook_marketplace_skill.py. Idempotent: safe to re-run.
"""

import asyncio

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models.agent import Agent
from app.models.credential import Credential
from app.models.grant import agent_credentials, agent_tools
from app.models.schedule import Schedule
from app.models.skill import Skill, agent_skills
from app.services.scheduler import compute_next_run
from app.services.skill_executor import invalidate_prompt_cache

AGENT_NAME = "Haifa Marketplace Scout"
AGENT_DESCRIPTION = "Daily Haifa-region rental scanner on Facebook Marketplace — reports to Noam and Tom."
SKILL_NAME = "Facebook Marketplace"
AGENT_PROMPT = """\
You are Haifa Marketplace Scout, a focused assistant that scans Facebook Marketplace for \
apartment rentals in the Haifa region (Haifa, Nesher, Kiryat Ata, Kiryat Motzkin, Kiryat Bialik).

Use facebook_marketplace_search with category="property_rentals" to find listings and \
facebook_marketplace_listing to read full details when a listing needs a closer look. These \
tools are read-only: you never post, message sellers, or change anything on the account.

You deliver findings over Telegram. The send_telegram tools are pre-bound to the right \
recipients — always send WITHOUT a chat_id argument so the message reaches everyone it should. \
If a call reports that the Facebook session hit a login wall, say that the facebook_session \
credential needs refreshing. Be concise and practical.
"""

TELEGRAM_TOOLS = ["send_telegram", "send_telegram_photo", "send_telegram_media_group"]
TELEGRAM_CREDENTIAL_NAMES = ["Noam telegram account", "Tom telegram account"]

OLD_YAD2_SCHEDULE_NAME = "Haifa real estate for tom"
SCHEDULE_NAME = "Daily Haifa region Marketplace rental scan"
CRON = "15 6 * * *"  # 06:15 UTC daily, staggered after the 06:00 Tel Aviv scans
SCHEDULE_INSTRUCTIONS = """\
Daily apartment scan — Haifa region rentals on Facebook Marketplace.

## Search
1. Call `facebook_marketplace_search` with `category="property_rentals"`, `location="haifa"`, \
`max_price=5500`, `sort_by="creation_time_descend"`, `limit=20`. The Haifa search radius also \
covers the Krayot — keep listings from Haifa, Nesher, Kiryat Ata, Kiryat Motzkin, and Kiryat \
Bialik; drop listings clearly elsewhere (e.g. Acre, Nahariya, Tirat Carmel is fine to keep if \
adjacent-Haifa, but skip anything far south or north). If the area is unclear, open the listing.
2. Keep only listings that match ALL of these requirements:
   - 3-4 rooms (Israeli "rooms"/חדרים, which counts the living room). Facebook counts BEDROOMS, \
so 2-3 bedrooms usually means 3-4 rooms — judge from the title/description first.
   - Price up to 5,500 ₪/mo including arnona.
   - Pet-friendly.
   - Has either a balcony or a garden.
   - Has a mamad (ממ"ד).
3. Room count, pets, balcony/garden, and mamad are usually in the description — call \
`facebook_marketplace_listing` on promising items to read the full text before deciding. If a \
required criterion is still unclear after reading the listing, skip it.
4. Shortlist the 3-5 best matches. Prefer better overall fit, better price, clearer listing \
details, and listings with images.

## Deliver each shortlisted listing to BOTH recipients (Noam + Tom)
Send once per listing with NO `chat_id` argument — the bound `chat_id` slot broadcasts to both \
accounts automatically. Never pass a `chat_id`, and never output a chat ID in your reply.

Photos: the search result carries one `image_url`. To attach more, call \
`facebook_marketplace_listing` for the item and use its `images` list. Then pick the tool:
- `images` has ≥2 URLs → `send_telegram_media_group` with up to 5 photos and a caption.
- exactly 1 photo → `send_telegram_photo` with a caption.
- no photos → `send_telegram` with a text message.

## Caption / message format (Markdown)
```
🏠 *[title]*
💰 *₪[price]/mo* · [area]
[short reason why it matches — rooms, pets, balcony/garden, mamad]

[Listing](listing_url)
```
Omit fields that are missing.

## Rules
- Price must be up to 5,500 ₪/mo including arnona.
- Listing must be pet-friendly, have a balcony or garden, and have a mamad.
- Source is Facebook Marketplace property rentals — do not use any other tool for this scan.
- If a search or listing call returns an ERROR (blocked, login wall, tool failure), report the \
error itself: send ONE `send_telegram` (no `chat_id`) saying the scan failed and why. Do NOT \
report "no matching listings" when the source errored.
- If the search worked and no listings survive the filters, still send ONE `send_telegram` \
(no `chat_id`) saying "No matching Haifa region listings today" rather than staying silent.
- Final reply: short summary — how many listings were delivered, to both accounts.
"""


async def seed():
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        # Upsert the agent.
        agent = (await session.execute(select(Agent).where(Agent.name == AGENT_NAME))).scalar_one_or_none()
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

        # Grant the Facebook Marketplace skill (brings the two read-only tools + session credential).
        skill = (await session.execute(select(Skill).where(Skill.name == SKILL_NAME))).scalar_one_or_none()
        if not skill:
            print(f"Skill '{SKILL_NAME}' not found — run seed_facebook_marketplace_skill first.")
            await engine.dispose()
            return
        await session.execute(
            pg_insert(agent_skills).values(agent_id=agent.id, skill_id=skill.id).on_conflict_do_nothing()
        )

        # Resolve the Telegram recipient credentials by name. Match on the trimmed name — some
        # stored credential names carry a trailing space (e.g. "Noam telegram account ").
        creds = (
            (
                await session.execute(
                    select(Credential).where(func.btrim(Credential.name).in_(TELEGRAM_CREDENTIAL_NAMES))
                )
            )
            .scalars()
            .all()
        )
        cred_by_name = {c.name.strip(): c for c in creds}
        missing = [n for n in TELEGRAM_CREDENTIAL_NAMES if n not in cred_by_name]
        if missing:
            print(f"WARNING: Telegram credentials not found: {missing}. Delivery will not reach them.")
        chat_ids = [str(cred_by_name[n].id) for n in TELEGRAM_CREDENTIAL_NAMES if n in cred_by_name]

        # Grant the recipient credentials directly (idempotent).
        for cred in creds:
            await session.execute(
                pg_insert(agent_credentials).values(agent_id=agent.id, credential_id=cred.id).on_conflict_do_nothing()
            )

        # Grant the three Telegram tools with chat_id bound to both recipients.
        for tool_name in TELEGRAM_TOOLS:
            stmt = pg_insert(agent_tools).values(
                agent_id=agent.id, tool_name=tool_name, slot_bindings={"chat_id": chat_ids}
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[agent_tools.c.agent_id, agent_tools.c.tool_name],
                set_={"slot_bindings": {"chat_id": chat_ids}},
            )
            await session.execute(stmt)
        await session.commit()
        print(f"Granted Telegram delivery ({', '.join(TELEGRAM_TOOLS)}) → {[c.name for c in creds]}")

        # Upsert the daily schedule.
        schedule = (
            await session.execute(select(Schedule).where(Schedule.name == SCHEDULE_NAME, Schedule.agent_id == agent.id))
        ).scalar_one_or_none()
        next_run = compute_next_run(CRON)
        if schedule:
            schedule.cron_expression = CRON
            schedule.instructions = SCHEDULE_INSTRUCTIONS
            schedule.enabled = True
            schedule.next_run_at = next_run
            print(f"Updated schedule: {SCHEDULE_NAME} (next run {next_run})")
        else:
            schedule = Schedule(
                agent_id=agent.id,
                name=SCHEDULE_NAME,
                cron_expression=CRON,
                instructions=SCHEDULE_INSTRUCTIONS,
                enabled=True,
                next_run_at=next_run,
            )
            session.add(schedule)
            print(f"Created schedule: {SCHEDULE_NAME} (next run {next_run})")

        # Retire the superseded Yad2 schedule (its source is bot-blocked and it mistargeted Tom).
        old = (
            await session.execute(select(Schedule).where(Schedule.name == OLD_YAD2_SCHEDULE_NAME))
        ).scalar_one_or_none()
        if old and old.enabled:
            old.enabled = False
            print(f"Disabled superseded schedule: {OLD_YAD2_SCHEDULE_NAME}")
        await session.commit()

        await invalidate_prompt_cache(agent.id)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
