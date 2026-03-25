"""Telegram bot integration — bridges Telegram messages to Gini agent loop."""
import asyncio
from uuid import UUID

import httpx
import structlog

from app.config import settings
from app.dependencies import async_session, redis_client
from app.models.agent import Agent
from app.models.agent_run import AgentRun
from app.models.conversation import Conversation
from app.models.message import Message
from app.services.llm_gateway import llm_gateway, LLMResponse
from app.services.skill_executor import get_assembled_prompt_with_credentials, get_assembled_prompt
from app.services.tool_runner import execute_tool
from app.tools.registry import get_llm_tool_specs
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

logger = structlog.get_logger("telegram")

TELEGRAM_API = "https://api.telegram.org/bot{token}"
MAX_TOOL_ROUNDS = 100
CHAT_MAP_PREFIX = "gini:telegram:chat:"
CHAT_AGENT_PREFIX = "gini:telegram:agent:"


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
            await client.post(f"{self.base_url}/setMyCommands", json={
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
            })

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

                except httpx.ReadTimeout:
                    continue
                except Exception as e:
                    await logger.aerror("telegram_poll_error", error=str(e))
                    await asyncio.sleep(5)

    # ── Message router ──────────────────────────────────────────────

    def _is_allowed(self, user_id: int) -> bool:
        """Check if a Telegram user is allowed to use the bot."""
        allowed = settings.telegram_allowed_users.strip()
        if not allowed:
            return True  # no restriction if not configured
        allowed_ids = {int(uid.strip()) for uid in allowed.split(",") if uid.strip()}
        return user_id in allowed_ids

    async def _handle_message(self, message: dict):
        chat_id = message["chat"]["id"]
        text = message["text"].strip()
        user_name = message["from"].get("first_name", "User")
        user_id = message["from"].get("id")

        if not self._is_allowed(user_id):
            await self._send_message(chat_id, "Access denied. Your Telegram account is not authorized to use this bot.")
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
                await handler(chat_id, user_name, arg)
                return
            # Unknown command — treat as regular message

        await self._handle_chat(chat_id, user_name, text)

    # ── Commands ────────────────────────────────────────────────────

    async def _cmd_start(self, chat_id: int, user_name: str, arg: str):
        await self._send_message(chat_id,
            f"👋 Hey {user_name}! I'm *Gini*, your AI assistant.\n\n"
            "Just send me a message and I'll help you out. I can use tools, "
            "run agents, fetch emails, send WhatsApp messages, and more.\n\n"
            "Type /help to see available commands."
        )

    async def _cmd_help(self, chat_id: int, user_name: str, arg: str):
        await self._send_message(chat_id,
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
            "Or just type a message to chat with me!"
        )

    async def _cmd_new(self, chat_id: int, user_name: str, arg: str):
        # Clear the conversation mapping so a new one is created
        await redis_client.delete(f"{CHAT_MAP_PREFIX}{chat_id}")
        # Also reset agent override
        await redis_client.delete(f"{CHAT_AGENT_PREFIX}{chat_id}")
        await self._send_message(chat_id, "🔄 Fresh conversation started! How can I help?")

    async def _cmd_agents(self, chat_id: int, user_name: str, arg: str):
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

        lines.append(f"\nSwitch with: /agent `<name>`")
        await self._send_message(chat_id, "\n".join(lines))

    async def _cmd_agent(self, chat_id: int, user_name: str, arg: str):
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

    async def _cmd_run(self, chat_id: int, user_name: str, arg: str):
        if not arg:
            await self._send_message(chat_id, "Usage: /run `<agent name>` `<task>`\n\nExample: /run Gmail IMAP Reader Fetch my 3 unread emails")
            return

        # Try to find agent name — match greedily against known agents
        async with async_session() as db:
            result = await db.execute(select(Agent).where(Agent.is_active == True).order_by(func.length(Agent.name).desc()))
            agents = result.scalars().all()

        matched_agent = None
        task = arg
        for a in agents:
            if arg.lower().startswith(a.name.lower()):
                matched_agent = a
                task = arg[len(a.name):].strip()
                break

        if not matched_agent:
            await self._send_message(chat_id, f"Couldn't find an agent in your command. Use /agents to list them.\n\nUsage: /run `<agent name>` `<task>`")
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
        await self._send_message(chat_id, f"🚀 Started *{matched_agent.name}*\n{'Task: ' + task if task else 'No specific instructions'}\n\nCheck status with /runs")

        # Wait for completion and notify
        asyncio.create_task(self._notify_run_complete(chat_id, run_id, matched_agent.name))

    async def _notify_run_complete(self, chat_id: int, run_id: str, agent_name: str):
        """Poll for run completion and send result to Telegram."""
        for _ in range(120):  # up to 6 minutes
            await asyncio.sleep(3)
            async with async_session() as db:
                run = await db.get(AgentRun, UUID(run_id))
                if not run:
                    return
                if run.status == "done":
                    result = run.result or "(no output)"
                    cost = f"${run.cost_usd:.4f}"
                    duration = f"{run.duration_ms/1000:.1f}s"
                    await self._send_long_message(chat_id,
                        f"✅ *{agent_name}* finished ({duration}, {cost})\n\n{result}"
                    )
                    return
                elif run.status == "failed":
                    error = run.error or "Unknown error"
                    await self._send_message(chat_id, f"❌ *{agent_name}* failed:\n{error[:500]}")
                    return

    async def _cmd_runs(self, chat_id: int, user_name: str, arg: str):
        async with async_session() as db:
            result = await db.execute(
                select(AgentRun)
                .options(selectinload(AgentRun.agent))
                .order_by(AgentRun.created_at.desc())
                .limit(5)
            )
            runs = result.scalars().all()

        if not runs:
            await self._send_message(chat_id, "No runs yet. Start one with /run `<agent>` `<task>`")
            return

        status_icons = {"done": "✅", "failed": "❌", "running": "⏳", "pending": "🕐"}
        lines = ["*Recent runs:*\n"]
        for r in runs:
            icon = status_icons.get(r.status, "❓")
            name = r.agent.name if r.agent else "?"
            task = (r.instructions or "no instructions")[:50]
            lines.append(f"{icon} *{name}* — {task}")
            if r.status == "done":
                lines.append(f"   ${r.cost_usd:.4f} · {r.duration_ms/1000:.1f}s")
            elif r.status == "failed" and r.error:
                lines.append(f"   {r.error[:60]}")

        await self._send_message(chat_id, "\n".join(lines))

    async def _cmd_history(self, chat_id: int, user_name: str, arg: str):
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

    async def _cmd_clear(self, chat_id: int, user_name: str, arg: str):
        # Delete the conversation mapping and Redis cache
        await redis_client.delete(f"{CHAT_MAP_PREFIX}{chat_id}")
        await redis_client.delete(f"{CHAT_AGENT_PREFIX}{chat_id}")
        await self._send_message(chat_id, "🗑 Conversation cleared. Send a message to start fresh.")

    async def _cmd_budget(self, chat_id: int, user_name: str, arg: str):
        async with async_session() as db:
            result = await db.execute(
                select(Agent).where(Agent.is_active == True).order_by(Agent.name)
            )
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

        if not self._is_allowed(message["from"].get("id")):
            await self._send_message(chat_id, "Access denied.")
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
                file_resp = await client.get(
                    f"https://api.telegram.org/file/bot{self.token}/{file_path}"
                )
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
            await self._handle_chat(chat_id, user_name, text)

        except Exception as e:
            await logger.aerror("voice_error", chat_id=chat_id, error=str(e))
            await self._send_message(chat_id, "Failed to process voice message. Please try again or type your message.")

    async def _handle_file_message(self, message: dict):
        """Handle photos and documents — describe the file to the agent."""
        chat_id = message["chat"]["id"]
        user_name = message["from"].get("first_name", "User")

        if not self._is_allowed(message["from"].get("id")):
            await self._send_message(chat_id, "Access denied.")
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
        await self._handle_chat(chat_id, user_name, text)

    # ── Chat handler ────────────────────────────────────────────────

    async def _handle_chat(self, chat_id: int, user_name: str, text: str):
        await self._send_action(chat_id, "typing")

        try:
            conversation_id = await self._get_or_create_conversation(chat_id, user_name)
            agent = await self._get_agent_for_chat(chat_id)
            if not agent:
                await self._send_message(chat_id, "No agent configured. Please set up a main agent in Gini.")
                return

            prompt_fn = get_assembled_prompt_with_credentials if agent.auto_approve else get_assembled_prompt
            system_prompt = await prompt_fn(agent)

            messages = await self._load_history(conversation_id)
            messages.append({"role": "user", "content": text})

            await self._persist_message(conversation_id, role="user", content=text)

            tool_specs = get_llm_tool_specs()
            response_text = await self._run_agent(agent, messages, system_prompt, tool_specs)

            await self._persist_message(conversation_id, role="assistant", content=response_text)
            await self._send_long_message(chat_id, response_text)

        except Exception as e:
            await logger.aerror("telegram_handle_error", chat_id=chat_id, error=str(e))
            await self._send_message(chat_id, "Sorry, something went wrong. Please try again.")

    # ── Agent loop ──────────────────────────────────────────────────

    async def _run_agent(
        self, agent: Agent, messages: list[dict], system_prompt: str, tool_specs: list[dict]
    ) -> str:
        for round_num in range(MAX_TOOL_ROUNDS):
            response: LLMResponse = await llm_gateway.call_with_tools(
                messages=messages,
                system_prompt=system_prompt,
                tools=tool_specs if tool_specs else None,
                provider=agent.llm_provider,
                model=agent.llm_model,
                temperature=agent.temperature,
                max_tokens=agent.max_tokens,
            )

            if not response.tool_calls:
                return response.content or "(no response)"

            assistant_content = []
            if response.content:
                assistant_content.append({"type": "text", "text": response.content})
            for tc in response.tool_calls:
                assistant_content.append({
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": tc["name"],
                    "input": tc["arguments"],
                })
            messages.append({"role": "assistant", "content": assistant_content})

            tool_results = []
            for tc in response.tool_calls:
                result = await execute_tool(tc["name"], tc["arguments"], use_sandbox=False)
                tool_output = result.output if result.success else f"Error: {result.error}"
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tc["id"],
                    "content": tool_output[:10000],
                })
            messages.append({"role": "user", "content": tool_results})

        return "I exceeded the maximum number of steps. Please try a simpler request."

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

    async def _get_or_create_conversation(self, chat_id: int, user_name: str) -> UUID:
        cached = await redis_client.get(f"{CHAT_MAP_PREFIX}{chat_id}")
        if cached:
            return UUID(cached)

        async with async_session() as db:
            result = await db.execute(
                select(Conversation).where(
                    Conversation.metadata_.contains({"telegram_chat_id": chat_id})
                ).order_by(Conversation.created_at.desc())
            )
            conv = result.scalar_one_or_none()
            if conv:
                await redis_client.set(f"{CHAT_MAP_PREFIX}{chat_id}", str(conv.id))
                return conv.id

            conv = Conversation(
                title=f"Telegram: {user_name}",
                metadata_={"telegram_chat_id": chat_id, "telegram_user": user_name},
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
                .where(Message.role.in_(["user", "assistant"]))
                .order_by(Message.created_at.desc())
                .limit(limit)
            )
            db_messages = list(reversed(result.scalars().all()))
            return [{"role": m.role, "content": m.content or ""} for m in db_messages]

    async def _persist_message(self, conversation_id: UUID, **kwargs):
        async with async_session() as db:
            msg = Message(conversation_id=conversation_id, **kwargs)
            db.add(msg)
            await db.commit()

    async def _send_message(self, chat_id: int, text: str):
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"{self.base_url}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
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


telegram_bot = TelegramBot()
