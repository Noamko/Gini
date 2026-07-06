"""Telegram bot integration — bridges Telegram messages to Gini agent loop."""

import asyncio
import contextlib
import json
from datetime import UTC, datetime
from uuid import UUID

import httpx
import structlog
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import selectinload

from app.config import settings
from app.dependencies import async_session, redis_client
from app.event_bus.hitl import get_pending_approvals, request_approval, resolve_approval, wait_for_approval
from app.models.agent import Agent
from app.models.agent_run import AgentRun
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.telegram_user import TelegramUser
from app.services import conversation_service
from app.services.agent_orchestrator import get_agent_by_name, run_sub_agent
from app.services.autonomous_execution import (
    AutonomousContext,
    run_autonomous_round,
)
from app.services.execution_prep import ExecutionResources, prepare_autonomous_resources

logger = structlog.get_logger("telegram")

TELEGRAM_API = "https://api.telegram.org/bot{token}"
MAX_TOOL_ROUNDS = 100
CHAT_MAP_PREFIX = "gini:telegram:chat:"
CHAT_AGENT_PREFIX = "gini:telegram:agent:"
APPROVAL_CALLBACK_PREFIX = "approval:"
PENDING_ACCESS_REPLY = "Hi! Your access request has been recorded and is pending approval."
SPEND_KEY_PREFIX = "gini:telegram:spend:"
SPEND_TTL_SECONDS = 48 * 3600


class TelegramBot:
    def __init__(self):
        self.token = settings.telegram_bot_token
        self.base_url = TELEGRAM_API.format(token=self.token)
        self._running = False
        self._offset = 0

    async def start(self):
        if not self.token or self.token == "your-telegram-bot-token-here":
            await logger.ainfo("telegram_disabled", reason="no token configured")
            return

        self._running = True
        await logger.ainfo("telegram_starting")

        # Verify bot token
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{self.base_url}/getMe")
            if resp.status_code != 200:
                await logger.aerror("telegram_auth_failed", status=resp.status_code)
                return
            me = resp.json()["result"]
            await logger.ainfo("telegram_connected", bot=me["username"])

            # Register commands
            await client.post(
                f"{self.base_url}/setMyCommands",
                json={
                    "commands": [
                        {"command": "start", "description": "Welcome & intro"},
                        {"command": "new", "description": "Start a fresh conversation"},
                        {"command": "agents", "description": "List available agents"},
                        {"command": "agent", "description": "Switch agent — /agent <name>"},
                        {"command": "run", "description": "Background run — /run <agent> <task>"},
                        {"command": "runs", "description": "Recent run statuses"},
                        {"command": "history", "description": "Show recent conversation history"},
                        {"command": "clear", "description": "Clear conversation history"},
                        {"command": "budget", "description": "Show agent cost budgets"},
                        {"command": "help", "description": "Show commands"},
                    ]
                },
            )

        await self._bootstrap_allowed_users()
        asyncio.create_task(self._poll_loop())

    async def stop(self):
        self._running = False

    async def _poll_loop(self):
        async with httpx.AsyncClient(timeout=35) as client:
            while self._running:
                try:
                    resp = await client.get(
                        f"{self.base_url}/getUpdates",
                        params={"offset": self._offset, "timeout": 30},
                    )
                    if resp.status_code != 200:
                        await asyncio.sleep(5)
                        continue

                    updates = resp.json().get("result", [])
                    for update in updates:
                        self._offset = update["update_id"] + 1
                        if "message" in update:
                            msg = update["message"]
                            if "text" in msg:
                                asyncio.create_task(self._handle_message(msg))
                            elif "voice" in msg or "audio" in msg:
                                asyncio.create_task(self._handle_voice_message(msg))
                            elif "document" in msg or "photo" in msg:
                                asyncio.create_task(self._handle_file_message(msg))
                        elif "callback_query" in update:
                            asyncio.create_task(self._handle_callback_query(update["callback_query"]))

                except httpx.ReadTimeout:
                    continue
                except Exception as e:
                    await logger.aerror("telegram_poll_error", error=str(e))
                    await asyncio.sleep(5)

    # ── Access control (DB-backed: telegram_users table) ────────────

    async def _bootstrap_allowed_users(self):
        """Seed telegram_users from TELEGRAM_ALLOWED_USERS as full-access operators.

        Idempotent (insert-if-missing); the table is the source of truth afterwards —
        the env var only matters on first boot. Must not crash startup on a flaky DB.
        """
        raw = settings.telegram_allowed_users.strip()
        if not raw:
            return
        ids = []
        for token in raw.split(","):
            token = token.strip()
            if not token:
                continue
            try:
                ids.append(int(token))
            except ValueError:
                await logger.awarning("telegram_acl_bootstrap_bad_token", token=token)
        if not ids:
            return
        try:
            async with async_session() as db:
                for telegram_id in ids:
                    stmt = (
                        pg_insert(TelegramUser)
                        .values(
                            telegram_id=telegram_id,
                            status="active",
                            can_chat=True,
                            can_receive=True,
                            can_approve=True,
                        )
                        .on_conflict_do_nothing(index_elements=["telegram_id"])
                    )
                    await db.execute(stmt)
                await db.commit()
            await logger.ainfo("telegram_acl_bootstrapped", count=len(ids))
        except Exception as e:
            await logger.awarning("telegram_acl_bootstrap_failed", error=str(e))

    async def _get_access(self, user_id: int) -> TelegramUser | None:
        async with async_session() as db:
            result = await db.execute(select(TelegramUser).where(TelegramUser.telegram_id == user_id))
            return result.scalar_one_or_none()

    async def _gate_message(self, message: dict) -> TelegramUser | None:
        """Inbound gate for text/voice/file messages.

        Returns the sender's row when they may chat (status active + can_chat), else None
        after registering unknown senders as pending. Handlers run as fire-and-forget
        tasks, so this never raises — a DB failure logs and denies (fail closed).
        """
        chat_id = message["chat"]["id"]
        sender = message.get("from") or {}
        user_id = sender.get("id")
        if user_id is None:
            return None
        try:
            user = await self._get_access(user_id)
            if user is None:
                await self._register_pending_user(user_id, sender)
                await self._send_message(chat_id, PENDING_ACCESS_REPLY)
                return None
            await self._touch_last_seen(user_id)
            if user.status == "active" and user.can_chat:
                return user
            if user.status == "pending":
                await self._send_message(chat_id, PENDING_ACCESS_REPLY)
            # Blocked (or active without can_chat): silence.
            return None
        except Exception as e:
            await logger.aerror("telegram_access_check_failed", user_id=user_id, error=str(e))
            return None

    async def _register_pending_user(self, user_id: int, sender: dict):
        async with async_session() as db:
            stmt = (
                pg_insert(TelegramUser)
                .values(
                    telegram_id=user_id,
                    username=sender.get("username"),
                    first_name=sender.get("first_name"),
                    last_name=sender.get("last_name"),
                    status="pending",
                    last_seen_at=datetime.now(UTC),
                )
                .on_conflict_do_nothing(index_elements=["telegram_id"])
            )
            await db.execute(stmt)
            await db.commit()
        await logger.ainfo("telegram_pending_registered", user_id=user_id, username=sender.get("username"))

    async def _touch_last_seen(self, user_id: int):
        """Best-effort last-seen bump; never blocks message handling."""
        try:
            async with async_session() as db:
                await db.execute(
                    update(TelegramUser)
                    .where(TelegramUser.telegram_id == user_id)
                    .values(last_seen_at=datetime.now(UTC))
                )
                await db.commit()
        except Exception as e:
            await logger.awarning("telegram_last_seen_failed", user_id=user_id, error=str(e))

    # ── Per-user daily spend (Redis counter; telegram chats have no AgentRun rows) ──

    def _spend_key(self, telegram_id: int) -> str:
        return f"{SPEND_KEY_PREFIX}{telegram_id}:{datetime.now(UTC):%Y-%m-%d}"

    async def _get_daily_spend(self, telegram_id: int) -> float:
        raw = await redis_client.get(self._spend_key(telegram_id))
        return float(raw) if raw else 0.0

    async def _record_spend(self, telegram_id: int, cost_usd: float):
        key = self._spend_key(telegram_id)
        await redis_client.incrbyfloat(key, cost_usd)
        await redis_client.expire(key, SPEND_TTL_SECONDS)

    async def _attribute_run_spend(self, telegram_user_id: int | None, cost_usd: float | None):
        """Count a /run's cost toward the invoking user's daily budget. Best-effort."""
        if telegram_user_id is None or not cost_usd:
            return
        try:
            await self._record_spend(telegram_user_id, cost_usd)
        except Exception as e:
            await logger.awarning("telegram_spend_record_failed", user_id=telegram_user_id, error=str(e))

    async def _budget_refusal(self, user: TelegramUser | None) -> str | None:
        """Refusal message when the user's daily budget is exhausted, else None."""
        if user is None or user.daily_budget_usd is None:
            return None
        spent = await self._get_daily_spend(user.telegram_id)
        if spent >= user.daily_budget_usd:
            return (
                f"You've reached your daily budget (${spent:.2f} of "
                f"${user.daily_budget_usd:.2f}). Please try again tomorrow."
            )
        return None

    # ── Message router ──────────────────────────────────────────────

    async def _handle_message(self, message: dict):
        chat_id = message["chat"]["id"]
        text = message["text"].strip()
        user_name = message["from"].get("first_name", "User")

        user = await self._gate_message(message)
        if user is None:
            return

        await logger.ainfo("telegram_message", chat_id=chat_id, user=user_name, text=text[:100])

        # Route commands
        if text.startswith("/"):
            parts = text.split(maxsplit=1)
            cmd = parts[0].lower().split("@")[0]  # strip @botname
            arg = parts[1] if len(parts) > 1 else ""

            handlers = {
                "/start": self._cmd_start,
                "/help": self._cmd_help,
                "/new": self._cmd_new,
                "/agents": self._cmd_agents,
                "/agent": self._cmd_agent,
                "/run": self._cmd_run,
                "/runs": self._cmd_runs,
                "/history": self._cmd_history,
                "/clear": self._cmd_clear,
                "/budget": self._cmd_budget,
            }
            handler = handlers.get(cmd)
            if handler:
                await handler(chat_id, user_name, arg, user)
                return
            # Unknown command — treat as regular message

        await self._handle_chat(chat_id, user_name, text, telegram_user=user)

    async def _handle_callback_query(self, callback_query: dict):
        chat_id = callback_query.get("message", {}).get("chat", {}).get("id")
        user_id = callback_query["from"].get("id")
        # Approval buttons require an active row with can_approve; unknown pressers are
        # NOT registered as pending (fail closed, including on DB errors).
        allowed = False
        try:
            user = await self._get_access(user_id) if user_id is not None else None
            allowed = user is not None and user.status == "active" and user.can_approve
        except Exception as e:
            await logger.aerror("telegram_access_check_failed", user_id=user_id, error=str(e))
        if not allowed:
            await self._answer_callback_query(
                callback_query["id"],
                "You are not authorized to approve actions.",
                show_alert=True,
            )
            return

        data = callback_query.get("data") or ""
        if not data.startswith(APPROVAL_CALLBACK_PREFIX):
            await self._answer_callback_query(callback_query["id"], "Unsupported action.")
            return

        parts = data.split(":", 2)
        if len(parts) != 3 or parts[1] not in {"approve", "reject"}:
            await self._answer_callback_query(callback_query["id"], "Unsupported action.")
            return

        approved = parts[1] == "approve"
        approval_id = parts[2]
        ok = await resolve_approval(
            approval_id,
            approved=approved,
            reason=None if approved else "Rejected from Telegram",
        )
        if not ok:
            await self._answer_callback_query(
                callback_query["id"],
                "This approval is no longer pending.",
                show_alert=True,
            )
            if chat_id and callback_query.get("message"):
                await self._edit_message_reply_markup(
                    chat_id,
                    callback_query["message"]["message_id"],
                    None,
                )
            return

        await self._answer_callback_query(
            callback_query["id"],
            "Approved. The agent will continue." if approved else "Rejected.",
        )
        if chat_id and callback_query.get("message"):
            status_line = "Approved via Telegram." if approved else "Rejected via Telegram."
            await self._edit_message_reply_markup(
                chat_id,
                callback_query["message"]["message_id"],
                None,
            )
            await self._send_message(chat_id, f"🛂 {status_line}")

    # ── Commands ────────────────────────────────────────────────────

    async def _cmd_start(self, chat_id: int, user_name: str, arg: str, user: TelegramUser):
        await self._send_message(
            chat_id,
            f"👋 Hey {user_name}! I'm *Gini*, your AI assistant.\n\n"
            "Just send me a message and I'll help you out. I can use tools, "
            "run agents, fetch emails, send WhatsApp messages, and more.\n\n"
            "Type /help to see available commands.",
        )

    async def _cmd_help(self, chat_id: int, user_name: str, arg: str, user: TelegramUser):
        await self._send_message(
            chat_id,
            "*Commands:*\n"
            "/new — Start a fresh conversation\n"
            "/agents — List available agents\n"
            "/agent `<name>` — Switch to a specific agent\n"
            "/run `<agent>` `<task>` — Run an agent in the background\n"
            "/runs — Show recent run statuses\n"
            "/history — Show recent messages\n"
            "/clear — Clear conversation history\n"
            "/budget — Show agent cost budgets\n"
            "/help — This message\n\n"
            "Or just type a message to chat with me!",
        )

    async def _cmd_new(self, chat_id: int, user_name: str, arg: str, user: TelegramUser):
        # Clear the conversation mapping so a new one is created
        await redis_client.delete(f"{CHAT_MAP_PREFIX}{chat_id}")
        # Also reset agent override
        await redis_client.delete(f"{CHAT_AGENT_PREFIX}{chat_id}")
        await self._send_message(chat_id, "🔄 Fresh conversation started! How can I help?")

    async def _cmd_agents(self, chat_id: int, user_name: str, arg: str, user: TelegramUser):
        async with async_session() as db:
            result = await db.execute(
                select(Agent).where(Agent.is_active == True).order_by(Agent.is_main.desc(), Agent.name)
            )
            agents = result.scalars().all()

        if not agents:
            await self._send_message(chat_id, "No agents configured.")
            return

        lines = ["*Available agents:*\n"]
        for a in agents:
            main = " 👑" if a.is_main else ""
            desc = f" — {a.description}" if a.description else ""
            lines.append(f"• `{a.name}`{main}{desc}")

        lines.append("\nSwitch with: /agent `<name>`")
        await self._send_message(chat_id, "\n".join(lines))

    async def _cmd_agent(self, chat_id: int, user_name: str, arg: str, user: TelegramUser):
        if not arg:
            # Show current agent
            current = await redis_client.get(f"{CHAT_AGENT_PREFIX}{chat_id}")
            if current:
                await self._send_message(chat_id, f"Currently using: `{current}`\n\nSwitch with: /agent `<name>`")
            else:
                await self._send_message(chat_id, "Using the default (main) agent.\n\nSwitch with: /agent `<name>`")
            return

        agent_name = arg.strip()
        async with async_session() as db:
            result = await db.execute(select(Agent).where(Agent.name.ilike(agent_name)))
            agent = result.scalar_one_or_none()

        if not agent:
            await self._send_message(chat_id, f"Agent `{agent_name}` not found. Use /agents to see available agents.")
            return

        await redis_client.set(f"{CHAT_AGENT_PREFIX}{chat_id}", agent.name)
        # Also start fresh conversation for the new agent
        await redis_client.delete(f"{CHAT_MAP_PREFIX}{chat_id}")
        await self._send_message(chat_id, f"✅ Switched to *{agent.name}*. New conversation started.")

    async def _cmd_run(self, chat_id: int, user_name: str, arg: str, user: TelegramUser):
        refusal = await self._budget_refusal(user)
        if refusal:
            await self._send_message(chat_id, refusal)
            return

        if not arg:
            await self._send_message(
                chat_id,
                "Usage: /run `<agent name>` `<task>`\n\nExample: /run Gmail IMAP Reader Fetch my 3 unread emails",
            )
            return

        # Try to find agent name — match greedily against known agents
        async with async_session() as db:
            result = await db.execute(
                select(Agent).where(Agent.is_active == True).order_by(func.length(Agent.name).desc())
            )
            agents = result.scalars().all()

        matched_agent = None
        task = arg
        for a in agents:
            if arg.lower().startswith(a.name.lower()):
                matched_agent = a
                task = arg[len(a.name) :].strip()
                break

        if not matched_agent:
            await self._send_message(
                chat_id,
                "Couldn't find an agent in your command. Use /agents to list them.\n\nUsage: /run `<agent name>` `<task>`",
            )
            return

        if not task:
            task = None

        # Create the run
        from app.api.runs import _execute_run

        async with async_session() as db:
            run = AgentRun(agent_id=matched_agent.id, instructions=task, status="pending")
            db.add(run)
            await db.commit()
            await db.refresh(run)
            run_id = str(run.id)

        asyncio.create_task(_execute_run(run_id, str(matched_agent.id)))
        await self._send_message(
            chat_id,
            f"🚀 Started *{matched_agent.name}*\n{'Task: ' + task if task else 'No specific instructions'}\n\nCheck status with /runs",
        )

        # Wait for completion and notify
        asyncio.create_task(
            self._notify_run_complete(chat_id, run_id, matched_agent.name, telegram_user_id=user.telegram_id)
        )

    async def _notify_run_complete(
        self, chat_id: int, run_id: str, agent_name: str, telegram_user_id: int | None = None
    ):
        """Poll for run completion and send result to Telegram."""
        surfaced_approval_ids: set[str] = set()
        for _ in range(120):  # up to 6 minutes
            await asyncio.sleep(3)
            async with async_session() as db:
                run = await db.get(AgentRun, UUID(run_id))
                if not run:
                    return
                if run.status == "done":
                    await self._attribute_run_spend(telegram_user_id, run.cost_usd)
                    result = run.result or "(no output)"
                    cost = f"${run.cost_usd:.4f}"
                    duration = f"{run.duration_ms / 1000:.1f}s"
                    await self._send_long_message(
                        chat_id, f"✅ *{agent_name}* finished ({duration}, {cost})\n\n{result}"
                    )
                    return
                elif run.status == "failed":
                    await self._attribute_run_spend(telegram_user_id, run.cost_usd)
                    error = run.error or "Unknown error"
                    await self._send_message(chat_id, f"❌ *{agent_name}* failed:\n{error[:500]}")
                    return
                elif run.status == "awaiting_approval":
                    approvals = await get_pending_approvals(run_id=run_id)
                    if approvals:
                        for approval in approvals:
                            if approval["id"] in surfaced_approval_ids:
                                continue
                            await self._send_approval_request(
                                chat_id,
                                approval,
                                title=f"Approval required for {agent_name}",
                            )
                            surfaced_approval_ids.add(approval["id"])
                    elif not surfaced_approval_ids:
                        await self._send_message(chat_id, f"🛂 *{agent_name}* is waiting for approval.")

    async def _cmd_runs(self, chat_id: int, user_name: str, arg: str, user: TelegramUser):
        async with async_session() as db:
            result = await db.execute(
                select(AgentRun).options(selectinload(AgentRun.agent)).order_by(AgentRun.created_at.desc()).limit(5)
            )
            runs = result.scalars().all()

        if not runs:
            await self._send_message(chat_id, "No runs yet. Start one with /run `<agent>` `<task>`")
            return

        status_icons = {"done": "✅", "failed": "❌", "running": "⏳", "pending": "🕐", "awaiting_approval": "🛂"}
        lines = ["*Recent runs:*\n"]
        for r in runs:
            icon = status_icons.get(r.status, "❓")
            name = r.agent.name if r.agent else "?"
            task = (r.instructions or "no instructions")[:50]
            lines.append(f"{icon} *{name}* — {task}")
            if r.status == "done":
                lines.append(f"   ${r.cost_usd:.4f} · {r.duration_ms / 1000:.1f}s")
            elif r.status == "failed" and r.error:
                lines.append(f"   {r.error[:60]}")

        await self._send_message(chat_id, "\n".join(lines))

    async def _cmd_history(self, chat_id: int, user_name: str, arg: str, user: TelegramUser):
        conversation_id = await self._get_or_create_conversation(chat_id, user_name)
        messages = await self._load_history(conversation_id, limit=10)
        if not messages:
            await self._send_message(chat_id, "No messages in this conversation yet.")
            return

        lines = ["*Recent messages:*\n"]
        for m in messages:
            role_icon = "👤" if m["role"] == "user" else "🤖"
            content = (m["content"] or "")[:150]
            lines.append(f"{role_icon} {content}")
        await self._send_long_message(chat_id, "\n".join(lines))

    async def _cmd_clear(self, chat_id: int, user_name: str, arg: str, user: TelegramUser):
        # Delete the conversation mapping and Redis cache
        await redis_client.delete(f"{CHAT_MAP_PREFIX}{chat_id}")
        await redis_client.delete(f"{CHAT_AGENT_PREFIX}{chat_id}")
        await self._send_message(chat_id, "🗑 Conversation cleared. Send a message to start fresh.")

    async def _cmd_budget(self, chat_id: int, user_name: str, arg: str, user: TelegramUser):
        async with async_session() as db:
            result = await db.execute(select(Agent).where(Agent.is_active == True).order_by(Agent.name))
            agents = result.scalars().all()

        lines = ["*Agent budgets:*\n"]
        for a in agents:
            if a.daily_budget_usd is not None:
                lines.append(f"• *{a.name}*: ${a.daily_budget_usd:.2f}/day")
            else:
                lines.append(f"• *{a.name}*: unlimited")
        await self._send_message(chat_id, "\n".join(lines))

    # ── File handler ──────────────────────────────────────────────────

    async def _handle_voice_message(self, message: dict):
        """Transcribe voice/audio messages and process as text."""
        chat_id = message["chat"]["id"]
        user_name = message["from"].get("first_name", "User")

        user = await self._gate_message(message)
        if user is None:
            return

        # Refuse before the (paid) Whisper transcription, not after.
        refusal = await self._budget_refusal(user)
        if refusal:
            await self._send_message(chat_id, refusal)
            return

        voice = message.get("voice") or message.get("audio")
        if not voice:
            return

        file_id = voice["file_id"]
        await self._send_action(chat_id, "typing")

        try:
            # Get file path from Telegram
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{self.base_url}/getFile", params={"file_id": file_id})
                file_path = resp.json()["result"]["file_path"]

                # Download the file
                file_resp = await client.get(f"https://api.telegram.org/file/bot{self.token}/{file_path}")
                audio_bytes = file_resp.content

            # Transcribe with OpenAI Whisper
            from openai import AsyncOpenAI

            from app.config import settings

            openai_client = AsyncOpenAI(api_key=settings.openai_api_key)

            # Whisper needs a file-like object with a name
            import io

            audio_file = io.BytesIO(audio_bytes)
            audio_file.name = "voice.ogg"

            transcription = await openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
            )
            text = transcription.text.strip()

            if not text:
                await self._send_message(chat_id, "Couldn't transcribe the voice message.")
                return

            await logger.ainfo("voice_transcribed", chat_id=chat_id, text=text[:100])
            await self._send_message(chat_id, f"🎤 _{text}_")

            # Process as regular chat message
            await self._handle_chat(chat_id, user_name, text, telegram_user=user)

        except Exception as e:
            await logger.aerror("voice_error", chat_id=chat_id, error=str(e))
            await self._send_message(chat_id, "Failed to process voice message. Please try again or type your message.")

    async def _handle_file_message(self, message: dict):
        """Handle photos and documents — describe the file to the agent."""
        chat_id = message["chat"]["id"]
        user_name = message["from"].get("first_name", "User")

        user = await self._gate_message(message)
        if user is None:
            return

        caption = message.get("caption", "")

        if "photo" in message:
            # Get the largest photo
            photo = message["photo"][-1]
            file_id = photo["file_id"]
            file_desc = f"[Photo received, file_id: {file_id}]"
        elif "document" in message:
            doc = message["document"]
            file_name = doc.get("file_name", "unknown")
            file_id = doc["file_id"]
            file_desc = f"[Document received: {file_name}, file_id: {file_id}]"
        else:
            return

        text = f"{file_desc}\n{caption}" if caption else file_desc
        await self._handle_chat(chat_id, user_name, text, telegram_user=user)

    # ── Chat handler ────────────────────────────────────────────────

    async def _handle_chat(self, chat_id: int, user_name: str, text: str, telegram_user: TelegramUser | None = None):
        await self._send_action(chat_id, "typing")

        try:
            refusal = await self._budget_refusal(telegram_user)
            if refusal:
                await self._send_message(chat_id, refusal)
                return

            telegram_user_id = telegram_user.telegram_id if telegram_user else None
            conversation_id = await self._get_or_create_conversation(
                chat_id, user_name, telegram_user_id=telegram_user_id
            )
            agent = await self._get_agent_for_chat(chat_id)
            if not agent:
                await self._send_message(chat_id, "No agent configured. Please set up a main agent in Gini.")
                return

            messages = await self._load_history(conversation_id)
            messages.append({"role": "user", "content": text})

            await self._persist_message(conversation_id, role="user", content=text)

            # Expose approval-gated tools (e.g. create_agent) — Telegram can now prompt for
            # approval via inline buttons, so include them even when the agent isn't auto-approve.
            resources = await prepare_autonomous_resources(agent, include_approval_tools=True)
            response_task = asyncio.create_task(
                self._run_agent(
                    agent,
                    messages,
                    resources,
                    conversation_id=str(conversation_id),
                    conversation_id_obj=conversation_id,
                    telegram_user_id=telegram_user_id,
                )
            )
            approval_watcher = asyncio.create_task(
                self._watch_conversation_approvals(chat_id, conversation_id, response_task)
            )
            try:
                response_text = await response_task
            finally:
                approval_watcher.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await approval_watcher

            await self._persist_message(conversation_id, role="assistant", content=response_text)
            await self._send_long_message(chat_id, response_text)

        except Exception as e:
            await logger.aerror("telegram_handle_error", chat_id=chat_id, error=str(e))
            await self._send_message(chat_id, "Sorry, something went wrong. Please try again.")

    # ── Agent loop ──────────────────────────────────────────────────

    async def _run_agent(
        self,
        agent: Agent,
        messages: list[dict],
        resources: ExecutionResources,
        conversation_id: str | None = None,
        conversation_id_obj: UUID | None = None,
        telegram_user_id: int | None = None,
    ) -> str:
        context = AutonomousContext(messages=messages)
        try:
            for round_num in range(MAX_TOOL_ROUNDS):

                async def persist_tool_round(content: str | None, assistant_content: list[dict]) -> None:
                    if conversation_id_obj:
                        await self._persist_message(
                            conversation_id_obj,
                            role="assistant",
                            content=content or "",
                            tool_calls=[block for block in assistant_content if block.get("type") == "tool_use"],
                            metadata={"hidden_from_ui": True, "message_kind": "tool_round"},
                        )

                async def persist_tool_result(
                    tool_name: str,
                    tc: dict,
                    tool_output: str,
                    _success: bool,
                    _error: str | None,
                ) -> None:
                    if conversation_id_obj:
                        await self._persist_message(
                            conversation_id_obj,
                            role="tool",
                            content=tool_output[:10000],
                            tool_call_id=tc["id"],
                            metadata={"hidden_from_ui": True, "tool_name": tool_name},
                        )

                async def delegate_task_runner(agent_name: str, task: str) -> dict:
                    sub_agent = await get_agent_by_name(agent_name)
                    if not sub_agent:
                        return {
                            "success": False,
                            "content": f"Error: Agent '{agent_name}' not found.",
                            "cost_usd": 0.0,
                        }
                    return await run_sub_agent(
                        agent=sub_agent,
                        task=task,
                        parent_conversation_id=conversation_id or "unknown",
                    )

                async def request_tool_approval(tc: dict, _tool_policy) -> tuple[bool, str | None]:
                    # Create a pending approval tied to this conversation. The approval watcher
                    # (_watch_conversation_approvals) surfaces it in Telegram with Approve/Reject
                    # buttons; the button callback resolves it and unblocks wait_for_approval.
                    pending = await request_approval(
                        tool_name=tc["name"],
                        arguments=tc["arguments"],
                        conversation_id=conversation_id,
                        agent_id=str(agent.id),
                        source="telegram",
                    )
                    approved = await wait_for_approval(pending, timeout=300)
                    return approved, pending.reject_reason

                round_result = await run_autonomous_round(
                    agent=agent,
                    resources=resources,
                    context=context,
                    round_num=round_num,
                    delegate_task_runner=delegate_task_runner,
                    request_tool_approval=request_tool_approval,
                    on_tool_round_persist=persist_tool_round,
                    on_tool_result=persist_tool_result,
                )
                if round_result.done:
                    return round_result.final_content or "(no response)"

            return "I exceeded the maximum number of steps. Please try a simpler request."
        finally:
            # Attribute this run's LLM spend to the triggering Telegram user (daily budget).
            if telegram_user_id is not None and context.total_cost_usd > 0:
                try:
                    await self._record_spend(telegram_user_id, context.total_cost_usd)
                except Exception as e:
                    await logger.awarning("telegram_spend_record_failed", user_id=telegram_user_id, error=str(e))

    # ── Helpers ──────────────────────────────────────────────────────

    async def _get_agent_for_chat(self, chat_id: int) -> Agent | None:
        """Get the agent for this chat — either overridden or main."""
        override = await redis_client.get(f"{CHAT_AGENT_PREFIX}{chat_id}")
        async with async_session() as db:
            if override:
                result = await db.execute(select(Agent).where(Agent.name == override))
                agent = result.scalar_one_or_none()
                if agent:
                    return agent
            result = await db.execute(select(Agent).where(Agent.is_main == True))
            return result.scalar_one_or_none()

    async def _get_or_create_conversation(
        self, chat_id: int, user_name: str, telegram_user_id: int | None = None
    ) -> UUID:
        cached = await redis_client.get(f"{CHAT_MAP_PREFIX}{chat_id}")
        if cached:
            return UUID(cached)

        async with async_session() as db:
            result = await db.execute(
                select(Conversation)
                .where(Conversation.metadata_.contains({"telegram_chat_id": chat_id}))
                .order_by(Conversation.created_at.desc())
            )
            conv = result.scalar_one_or_none()
            if conv:
                await redis_client.set(f"{CHAT_MAP_PREFIX}{chat_id}", str(conv.id))
                return conv.id

            metadata = {"telegram_chat_id": chat_id, "telegram_user": user_name}
            if telegram_user_id is not None:
                metadata["telegram_user_id"] = telegram_user_id
            conv = Conversation(
                title=f"Telegram: {user_name}",
                metadata_=metadata,
            )
            db.add(conv)
            await db.commit()
            await db.refresh(conv)
            await redis_client.set(f"{CHAT_MAP_PREFIX}{chat_id}", str(conv.id))
            return conv.id

    async def _get_main_agent(self) -> Agent | None:
        async with async_session() as db:
            result = await db.execute(select(Agent).where(Agent.is_main == True))
            return result.scalar_one_or_none()

    async def _load_history(self, conversation_id: UUID, limit: int = 20) -> list[dict]:
        async with async_session() as db:
            result = await db.execute(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.desc())
                .limit(limit)
            )
            db_messages = list(reversed(result.scalars().all()))
            return conversation_service.build_llm_history(db_messages)

    async def _persist_message(self, conversation_id: UUID, **kwargs):
        async with async_session() as db:
            await conversation_service.create_message(db, conversation_id=conversation_id, **kwargs)

    async def _watch_conversation_approvals(
        self,
        chat_id: int,
        conversation_id: UUID,
        response_task: asyncio.Task,
    ) -> None:
        surfaced_ids: set[str] = set()
        while not response_task.done():
            approvals = await get_pending_approvals(conversation_id=str(conversation_id))
            for approval in approvals:
                approval_id = approval["id"]
                if approval_id in surfaced_ids:
                    continue
                await self._send_approval_request(chat_id, approval)
                surfaced_ids.add(approval_id)
            await asyncio.sleep(1)

    def _approval_markup(self, approval_id: str) -> dict:
        return {
            "inline_keyboard": [
                [
                    {"text": "Approve", "callback_data": f"{APPROVAL_CALLBACK_PREFIX}approve:{approval_id}"},
                    {"text": "Reject", "callback_data": f"{APPROVAL_CALLBACK_PREFIX}reject:{approval_id}"},
                ]
            ]
        }

    async def _send_approval_request(self, chat_id: int, approval: dict, title: str = "Approval required"):
        tool_name = approval.get("tool_name", "unknown")
        # Only render Approve/Reject buttons in chats whose telegram_users row may
        # approve — buttons the callback gate would refuse anyway are just confusing.
        can_approve = False
        try:
            user = await self._get_access(chat_id)
            can_approve = user is not None and user.status == "active" and user.can_approve
        except Exception as e:
            await logger.aerror("telegram_access_check_failed", user_id=chat_id, error=str(e))
        if not can_approve:
            await self._send_message(chat_id, f"⏳ `{tool_name}` requires approval from an operator.")
            return

        arguments = json.dumps(approval.get("arguments", {}), indent=2, ensure_ascii=True)
        text = (
            f"🛂 *{title}*\n"
            f"Tool: `{tool_name}`\n"
            f"Approval ID: `{approval['id']}`\n"
            f"Arguments:\n```json\n{arguments[:2500]}\n```"
        )
        await self._send_message(
            chat_id,
            text,
            reply_markup=self._approval_markup(approval["id"]),
        )

    async def _send_message(self, chat_id: int, text: str, reply_markup: dict | None = None):
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"{self.base_url}/sendMessage",
                json=payload,
            )

    async def _send_long_message(self, chat_id: int, text: str):
        if len(text) <= 4096:
            await self._send_message(chat_id, text)
            return
        chunks = []
        current = ""
        for line in text.split("\n"):
            if len(current) + len(line) + 1 > 4000:
                chunks.append(current)
                current = line
            else:
                current = current + "\n" + line if current else line
        if current:
            chunks.append(current)
        for chunk in chunks:
            await self._send_message(chat_id, chunk)
            await asyncio.sleep(0.3)

    async def _send_action(self, chat_id: int, action: str = "typing"):
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(
                    f"{self.base_url}/sendChatAction",
                    json={"chat_id": chat_id, "action": action},
                )
        except Exception:
            pass

    async def _answer_callback_query(self, callback_query_id: str, text: str, show_alert: bool = False):
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"{self.base_url}/answerCallbackQuery",
                json={
                    "callback_query_id": callback_query_id,
                    "text": text,
                    "show_alert": show_alert,
                },
            )

    async def _edit_message_reply_markup(
        self,
        chat_id: int,
        message_id: int,
        reply_markup: dict | None,
    ):
        payload = {"chat_id": chat_id, "message_id": message_id}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(f"{self.base_url}/editMessageReplyMarkup", json=payload)


telegram_bot = TelegramBot()
