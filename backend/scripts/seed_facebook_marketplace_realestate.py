"""Wire the Marketplace Scout agent for the daily Tel Aviv rental scan.

Mirrors the Yad2 "Real Estate Agent" morning scan for Facebook Marketplace:
  1. Grants Marketplace Scout the three send_telegram tools, with their ``chat_id`` slot
     bound to the Noam + Gili Telegram credentials (so a send with no chat_id broadcasts to both),
     plus direct grants of those two credentials.
  2. Creates a daily schedule ("Daily central Tel Aviv Marketplace rental scan", 06:00 UTC) whose
     instructions apply the same filter set as the Yad2 scan (3+ rooms, 6000-9000 ILS, central TA),
     using the Property Rentals category, and delivers matches to both Telegram accounts.

Run AFTER seed_facebook_marketplace_agent.py. Idempotent: safe to re-run.
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
from app.services.scheduler import compute_next_run
from app.services.skill_executor import invalidate_prompt_cache

AGENT_NAME = "Marketplace Scout"
TELEGRAM_TOOLS = ["send_telegram", "send_telegram_photo", "send_telegram_media_group"]
# Same recipients as the Yad2 central Tel Aviv scan.
TELEGRAM_CREDENTIAL_NAMES = ["Noam telegram account", "Gili Telegram account Id"]

SCHEDULE_NAME = "Daily central Tel Aviv Marketplace rental scan"
CRON = "0 6 * * *"  # 06:00 UTC daily — same time as the Yad2 scan
SCHEDULE_INSTRUCTIONS = """\
Daily apartment scan — central Tel Aviv rentals on Facebook Marketplace.

## Search
1. Call `facebook_marketplace_search` with `category="property_rentals"`, `location="tel aviv"`, \
`min_price=6000`, `max_price=9000`, `sort_by="creation_time_descend"`, `limit=20`.
2. Keep only apartments with 3 or more rooms (Israeli "rooms"/חדרים, which counts the living room). \
Judge from the title/description — listings usually state the room count (e.g. "3 חדרים", "4 rooms"). \
If a listing is promising but the room count is unclear, call `facebook_marketplace_listing` to read \
the full detail before deciding. If still unclear, skip it.
3. Keep only listings in central Tel Aviv neighborhoods — Lev Ha'ir, Rothschild / Sheinkin, Florentin, \
Neve Tzedek, Kerem HaTeimanim, Dizengoff, Old North (HaTzafon HaYashan). Judge from the title, \
description, and location text; if the area is clearly elsewhere (e.g. Givatayim, Holon, Netanya, \
Bat Yam, Jaffa outskirts), drop it. If unclear, skip.
4. Drop anything priced under 6000 or over 9000 ₪/mo.
5. Shortlist the 3-5 best matches. Prefer closer to Rothschild / Dizengoff, better price-per-room, \
and listings that have images.

## Deliver each shortlisted listing to BOTH Telegram accounts (Noam + Gili)
Send once per listing with NO `chat_id` argument — the bound `chat_id` slot broadcasts to both \
accounts automatically. Never pass a `chat_id`, and never output a chat ID in your reply.

Photos: the search result carries one `image_url`. To attach more, call `facebook_marketplace_listing` \
for the item and use its `images` list. Then pick the tool:
- `images` has ≥2 URLs → `send_telegram_media_group` with up to 5 photos and a caption.
- exactly 1 photo → `send_telegram_photo` with a caption.
- no photos → `send_telegram` with a text message.

## Caption / message format (Markdown)
```
🏠 *[title]*
💰 *₪[price]/mo* · [area]
[short reason why it matches — rooms, neighborhood, standout feature]

[Listing](listing_url)
```
Omit fields that are missing.

## Rules
- Price must be between 6000 and 9000 ₪/mo inclusive.
- Source is Facebook Marketplace property rentals — do not use any other tool for this scan.
- If no listings survive the filters, still send ONE `send_telegram` (no `chat_id`) saying \
"No central Tel Aviv Marketplace rentals today" rather than staying silent.
- Final reply: short summary — how many listings were delivered, to both accounts.
"""


async def seed():
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        agent = (await session.execute(select(Agent).where(Agent.name == AGENT_NAME))).scalar_one_or_none()
        if not agent:
            print(f"Agent '{AGENT_NAME}' not found — run seed_facebook_marketplace_agent first.")
            await engine.dispose()
            return

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
        await session.commit()

        await invalidate_prompt_cache(agent.id)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
