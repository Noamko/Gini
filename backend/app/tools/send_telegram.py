from typing import Any

import httpx
import structlog
from sqlalchemy import select

from app.config import settings
from app.dependencies import async_session
from app.models.telegram_user import TelegramUser
from app.tools.base import BaseTool, CredentialSlot, ToolResult

logger = structlog.get_logger("tools.send_telegram")

# Slot holding the default Telegram chat(s) to send to when the caller omits a numeric one.
# It is a ``multi`` slot: bind one or more chat credentials and every message fans out to all of them.
_TELEGRAM_CHAT_SLOT = CredentialSlot(
    name="chat_id",
    type="telegram",
    required=False,
    multi=True,
    description="Default Telegram chat(s) to send to when chat_id is omitted. Binds one or more; broadcasts to all.",
)


def _resolve_chat_ids(chat_id: str | None, credential_values: dict[str, Any] | None) -> list[str]:
    """Resolve the target chats: an explicit numeric literal if given, else every bound ``chat_id`` slot."""
    if chat_id:
        stripped = str(chat_id).strip()
        if stripped.lstrip("-").isdigit():
            return [stripped]
    bound = (credential_values or {}).get("chat_id")
    if bound is None:
        return []
    values = bound if isinstance(bound, list) else [bound]
    return [v for v in (str(b).strip() for b in values) if v]


async def _refused_recipients(targets: list[str]) -> dict[str, str]:
    """Map target → failure reason for recipients registered in telegram_users but not permitted.

    A target is refused when its row exists and (status != "active" or can_receive is off).
    Unregistered ids stay allowed: admin-bound credentials imply consent, and groups/channels
    are typically unregistered. One query covers all targets; a DB failure logs and allows
    (fails open) so delivery keeps working.
    """
    numeric: dict[int, str] = {}
    for target in targets:
        stripped = target.strip()
        if stripped.lstrip("-").isdigit():
            numeric[int(stripped)] = target
    if not numeric:
        return {}
    try:
        async with async_session() as db:
            result = await db.execute(select(TelegramUser).where(TelegramUser.telegram_id.in_(numeric)))
            rows = result.scalars().all()
    except Exception as e:
        await logger.awarning("telegram_recipient_check_failed", error=str(e))
        return {}
    return {
        numeric[row.telegram_id]: f"recipient {numeric[row.telegram_id]} not permitted"
        for row in rows
        if row.status != "active" or not row.can_receive
    }


async def _broadcast(*, token: str, targets: list[str], path: str, payload_for, timeout: float, summary) -> ToolResult:
    """POST ``path`` once per target with ``payload_for(chat_id)``; aggregate the results.

    Succeeds if at least one chat received the message (so a single bad chat id doesn't drop
    delivery to the rest); any failures are surfaced in the output and metadata.
    """
    successes: list[tuple[str, dict]] = []
    failures: list[tuple[str, str]] = []
    refused = await _refused_recipients(targets)
    async with httpx.AsyncClient(timeout=timeout) as client:
        for cid in targets:
            if cid in refused:
                failures.append((cid, refused[cid]))
                continue
            try:
                resp = await client.post(f"https://api.telegram.org/bot{token}/{path}", json=payload_for(cid))
                data = resp.json()
            except Exception as e:
                failures.append((cid, str(e)))
                continue
            if data.get("ok"):
                successes.append((cid, data["result"]))
            else:
                failures.append((cid, data.get("description", "Unknown error")))

    if not successes:
        detail = "; ".join(f"{c}: {e}" for c, e in failures) or "no chats targeted"
        return ToolResult(success=False, error=f"Telegram send failed for all targets ({detail})")

    output = summary(successes)
    if failures:
        output += " | failed for " + "; ".join(f"{c}: {e}" for c, e in failures)
    return ToolResult(
        output=output,
        metadata={
            "chat_ids": [c for c, _ in successes],
            "failures": {c: e for c, e in failures},
        },
    )


class SendTelegramTool(BaseTool):
    name = "send_telegram"
    description = "Send a text message to a Telegram chat. Targets the bound chat unless a numeric chat_id is given."
    credential_slots = [_TELEGRAM_CHAT_SLOT]
    parameters_schema = {
        "type": "object",
        "properties": {
            "chat_id": {
                "type": "string",
                "description": "Numeric Telegram chat ID. Optional — if omitted, the chat bound to this tool is used.",
            },
            "text": {
                "type": "string",
                "description": "The message text to send.",
            },
        },
        "required": ["text"],
    }

    async def execute(
        self, text: str, chat_id: str | None = None, credential_values: dict[str, Any] | None = None, **kwargs: Any
    ) -> ToolResult:
        token = settings.telegram_bot_token
        if not token or token == "your-telegram-bot-token-here":
            return ToolResult(success=False, error="Telegram bot token not configured")

        targets = _resolve_chat_ids(chat_id, credential_values)
        if not targets:
            return ToolResult(
                success=False,
                error=f"Could not resolve chat_id '{chat_id}' — not numeric and no chat credential bound.",
            )

        return await _broadcast(
            token=token,
            targets=targets,
            path="sendMessage",
            payload_for=lambda cid: {"chat_id": cid, "text": text, "parse_mode": "Markdown"},
            timeout=10,
            summary=lambda s: f"Message sent to {len(s)} chat(s) (message_ids: {[r['message_id'] for _, r in s]})",
        )


class SendTelegramPhotoTool(BaseTool):
    name = "send_telegram_photo"
    description = "Send a photo to a Telegram chat by URL. Targets the bound chat unless a numeric chat_id is given."
    credential_slots = [_TELEGRAM_CHAT_SLOT]
    parameters_schema = {
        "type": "object",
        "properties": {
            "chat_id": {
                "type": "string",
                "description": "Numeric Telegram chat ID. Optional — if omitted, the chat bound to this tool is used.",
            },
            "photo_url": {
                "type": "string",
                "description": "URL of the photo to send.",
            },
            "caption": {
                "type": "string",
                "description": "Optional caption for the photo.",
            },
        },
        "required": ["photo_url"],
    }

    async def execute(
        self,
        photo_url: str,
        caption: str = "",
        chat_id: str | None = None,
        credential_values: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        token = settings.telegram_bot_token
        if not token or token == "your-telegram-bot-token-here":
            return ToolResult(success=False, error="Telegram bot token not configured")

        targets = _resolve_chat_ids(chat_id, credential_values)
        if not targets:
            return ToolResult(
                success=False,
                error=f"Could not resolve chat_id '{chat_id}' — not numeric and no chat credential bound.",
            )

        def payload_for(cid: str) -> dict:
            payload: dict = {"chat_id": cid, "photo": photo_url}
            if caption:
                payload["caption"] = caption[:1024]
                payload["parse_mode"] = "Markdown"
            return payload

        return await _broadcast(
            token=token,
            targets=targets,
            path="sendPhoto",
            payload_for=payload_for,
            timeout=15,
            summary=lambda s: f"Photo sent to {len(s)} chat(s) (message_ids: {[r['message_id'] for _, r in s]})",
        )


class SendTelegramMediaGroupTool(BaseTool):
    name = "send_telegram_media_group"
    description = "Send multiple photos as an album to a Telegram chat. Targets the bound chat unless a numeric chat_id is given. Max 10 photos per group."
    credential_slots = [_TELEGRAM_CHAT_SLOT]
    parameters_schema = {
        "type": "object",
        "properties": {
            "chat_id": {
                "type": "string",
                "description": "Numeric Telegram chat ID. Optional — if omitted, the chat bound to this tool is used.",
            },
            "photo_urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of photo URLs to send as an album (max 10).",
            },
            "caption": {
                "type": "string",
                "description": "Caption for the first photo in the album.",
            },
        },
        "required": ["photo_urls"],
    }

    async def execute(
        self,
        photo_urls: list[str],
        caption: str = "",
        chat_id: str | None = None,
        credential_values: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        token = settings.telegram_bot_token
        if not token or token == "your-telegram-bot-token-here":
            return ToolResult(success=False, error="Telegram bot token not configured")

        if not photo_urls:
            return ToolResult(success=False, error="No photo URLs provided")

        targets = _resolve_chat_ids(chat_id, credential_values)
        if not targets:
            return ToolResult(
                success=False,
                error=f"Could not resolve chat_id '{chat_id}' — not numeric and no chat credential bound.",
            )

        urls = photo_urls[:10]
        media = []
        for i, url in enumerate(urls):
            item: dict = {"type": "photo", "media": url}
            if i == 0 and caption:
                item["caption"] = caption[:1024]
                item["parse_mode"] = "Markdown"
            media.append(item)

        return await _broadcast(
            token=token,
            targets=targets,
            path="sendMediaGroup",
            payload_for=lambda cid: {"chat_id": cid, "media": media},
            timeout=20,
            summary=lambda s: f"Album ({len(urls)} photos) sent to {len(s)} chat(s)",
        )
