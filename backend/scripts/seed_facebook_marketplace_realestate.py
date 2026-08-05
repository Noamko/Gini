"""Wire the Marketplace Scout agent for the unified daily Tel Aviv rental scan.

One scan, three sources — Yad2, Facebook Marketplace, and the account's Facebook rental groups
(this replaced the separate Yad2 "Real Estate Agent" TA scan, now disabled):
  1. Grants Marketplace Scout the three send_telegram tools, with their ``chat_id`` slot
     bound to the Noam + Gili Telegram credentials (so a send with no chat_id broadcasts to both),
     plus direct grants of those two credentials, plus ``yad2_search``.
  2. Creates the twice-daily schedule ("Daily central Tel Aviv rental scan (Yad2 + Marketplace +
     groups)", 06:00 + 17:00 UTC) applying one shared filter set (3+ rooms, 6000-9000 ILS, central
     TA), deduping across sources, and delivering EVERY match to both Telegram accounts (no
     shortlist cap).

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

SCHEDULE_NAME = "Daily central Tel Aviv rental scan (Yad2 + Marketplace + groups)"
CRON = "0 6,17 * * *"  # 06:00 + 17:00 UTC daily
SCHEDULE_INSTRUCTIONS = """\
Daily apartment scan — central Tel Aviv rentals from THREE sources: Yad2, Facebook Marketplace, and \
the account's Facebook rental groups. Deliver EVERY apartment that passes the filters — there is no \
cap on the number of results.

## Shared filters (apply to every source)
- Monthly rent between 6000 and 9000 ₪ inclusive.
- 3 or more rooms (Israeli "rooms"/חדרים, which counts the living room).
- Central Tel Aviv neighborhoods only — Lev Ha'ir, Rothschild / Sheinkin, Florentin, Neve Tzedek, \
Kerem HaTeimanim, Dizengoff, Old North (HaTzafon HaYashan). If the area is clearly elsewhere \
(e.g. Givatayim, Holon, Netanya, Bat Yam, Jaffa outskirts), drop it; if unclear, skip.
- Apartments OFFERED for rent only — drop "looking for"/מחפש/מחפשת posts, roommate-wanted posts, \
and short sublets of a few days.

## Source 1 — Yad2
1. Call `yad2_search` with `city="tel aviv"`, `min_rooms=3`, `max_price=9000`, `limit=10`.
2. Drop price < 6000, then apply the shared filters (use the address / maps link to judge the \
neighborhood when the neighborhood field is empty).
3. If `yad2_search` fails with a bot-verification / Radware error, do NOT retry — the verdict is \
per-request from this IP and fingerprint, so a retry returns the same block. Send one \
`send_telegram` (no `chat_id`) saying "⚠️ Yad2 blocked today's automated scan — Yad2 listings \
unavailable (this is not an empty market)." and continue with the other sources.

## Source 2 — Facebook Marketplace
1. Call `facebook_marketplace_search` with `category="property_rentals"`, `location="tel aviv"`, \
`min_price=6000`, `max_price=9000`, `sort_by="creation_time_descend"`, `limit=30`.
2. Apply the shared filters. Judge rooms from the title/description; if a listing is promising but \
the room count or area is unclear, call `facebook_marketplace_listing` to read the full detail. \
If still unclear, skip it.

## Source 3 — Facebook groups
1. Call `facebook_group_list` (no query). Pick every group whose name indicates Tel Aviv apartment \
rentals — Hebrew or English (e.g. names containing דירות, השכרה, שכירות, תל אביב, "Tel Aviv", \
"rent", "apartments"). Ignore groups clearly about something else or another city.
2. Call `facebook_group_posts` with those groups, `posts_per_group=10` — at most 10 groups per \
call; if more matched, make additional calls in batches of 10.
3. Keep posts with `age_hours` of 12 or less (the scan runs twice a day, so older posts were \
covered by the previous run) that pass the shared filters, judged from the post text (usually \
Hebrew).
4. If the group tools fail with a login-wall / expired-session error, skip this source (no retry, \
no Telegram error message) and note it briefly in your final reply.

## Cross-source dedupe
The same apartment often appears in more than one source (and in several groups). Same address + \
same price + same photos = same apartment: send it ONCE, preferring the most detailed version \
(Yad2 structured listing > Marketplace listing > group post).

## Delivery — EVERY match, to BOTH Telegram accounts (Noam + Gili)
Send once per apartment with NO `chat_id` argument — the bound `chat_id` slot broadcasts to both \
accounts automatically. Never pass a `chat_id`, and never output a chat ID or credential name.

Photos per listing: Yad2 → `image_urls`; Marketplace → the search `image_url`, or call \
`facebook_marketplace_listing` for the full `images` list; group posts → `image_url`. Then pick \
the tool:
- ≥2 photo URLs → `send_telegram_media_group` with up to 5 photos and a caption.
- exactly 1 photo → `send_telegram_photo` with a caption.
- no photos → `send_telegram` with a text message.

## Caption / message format (Markdown)
```
🏠 *[address or title / first line of post]*
💰 *₪[price]/mo* · [rooms] rooms · [neighborhood]
[short reason why it matches — rooms, neighborhood, standout feature]

[Listing](url)  ·  [Map](google_maps_url)
```
Omit fields that are missing (the map link exists only for Yad2). For group posts, link the \
`post_url` and mention the group name.

## Rules
- Sources are exactly: `yad2_search`, the Facebook Marketplace tools, and the Facebook group \
tools — do not use any other tool for this scan.
- Deliver every apartment that passes the filters — do NOT cut the list down to a "best of" \
shortlist.
- If NOTHING from any source survives the filters, still send ONE `send_telegram` (no `chat_id`) \
saying "No central Tel Aviv rentals today (Yad2 + Marketplace + groups)" rather than staying \
silent.
- Final reply: short summary — how many apartments were delivered per source, and any source that \
was blocked or skipped.
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
        # Grant yad2_search (no slot bindings) so the scan covers Yad2 too.
        await session.execute(
            pg_insert(agent_tools)
            .values(agent_id=agent.id, tool_name="yad2_search", slot_bindings={})
            .on_conflict_do_nothing()
        )
        await session.commit()
        print(f"Granted Telegram delivery ({', '.join(TELEGRAM_TOOLS)}) + yad2_search → {[c.name for c in creds]}")

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
