from typing import Any

import httpx

from app.config import settings
from app.tools.base import BaseTool, ToolResult


def _resolve_chat_id(chat_id: str, credential_values: dict[str, str] | None) -> str | None:
    """Resolve chat_id: literal if numeric, otherwise look up as a credential name.

    Credential keys are compared trimmed and case-insensitive so trailing spaces
    or casing differences between the agent's argument and the stored name do not
    break resolution.
    """
    if not chat_id:
        return None
    stripped = chat_id.strip()
    if stripped.lstrip("-").isdigit():
        return stripped
    if credential_values:
        normalized = {k.strip().lower(): v for k, v in credential_values.items()}
        value = normalized.get(stripped.lower())
        if value:
            return value.strip()
    return None


class SendTelegramTool(BaseTool):
    name = "send_telegram"
    description = "Send a text message to a Telegram chat. chat_id can be a numeric chat ID or the name of a Telegram credential to resolve."
    parameters_schema = {
        "type": "object",
        "properties": {
            "chat_id": {
                "type": "string",
                "description": "Numeric Telegram chat ID, or the name of a Telegram credential (e.g. 'Noam telegram account').",
            },
            "text": {
                "type": "string",
                "description": "The message text to send.",
            },
        },
        "required": ["chat_id", "text"],
    }

    async def execute(self, chat_id: str, text: str, credential_values: dict[str, str] | None = None, **kwargs: Any) -> ToolResult:
        token = settings.telegram_bot_token
        if not token or token == "your-telegram-bot-token-here":
            return ToolResult(success=False, error="Telegram bot token not configured")

        resolved = _resolve_chat_id(chat_id, credential_values)
        if not resolved:
            return ToolResult(success=False, error=f"Could not resolve chat_id '{chat_id}' — not numeric and not a known credential.")

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": resolved, "text": text, "parse_mode": "Markdown"},
                )
                data = resp.json()
                if data.get("ok"):
                    msg_id = data["result"]["message_id"]
                    return ToolResult(
                        output=f"Message sent successfully (message_id: {msg_id})",
                        metadata={"message_id": msg_id, "chat_id": resolved},
                    )
                else:
                    return ToolResult(
                        success=False,
                        error=f"Telegram API error: {data.get('description', 'Unknown error')}",
                    )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class SendTelegramPhotoTool(BaseTool):
    name = "send_telegram_photo"
    description = "Send a photo to a Telegram chat by URL. chat_id can be a numeric chat ID or the name of a Telegram credential to resolve."
    parameters_schema = {
        "type": "object",
        "properties": {
            "chat_id": {
                "type": "string",
                "description": "Numeric Telegram chat ID, or the name of a Telegram credential.",
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
        "required": ["chat_id", "photo_url"],
    }

    async def execute(self, chat_id: str, photo_url: str, caption: str = "", credential_values: dict[str, str] | None = None, **kwargs: Any) -> ToolResult:
        token = settings.telegram_bot_token
        if not token or token == "your-telegram-bot-token-here":
            return ToolResult(success=False, error="Telegram bot token not configured")

        resolved = _resolve_chat_id(chat_id, credential_values)
        if not resolved:
            return ToolResult(success=False, error=f"Could not resolve chat_id '{chat_id}' — not numeric and not a known credential.")

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                payload: dict = {"chat_id": resolved, "photo": photo_url}
                if caption:
                    payload["caption"] = caption[:1024]
                    payload["parse_mode"] = "Markdown"

                resp = await client.post(
                    f"https://api.telegram.org/bot{token}/sendPhoto",
                    json=payload,
                )
                data = resp.json()
                if data.get("ok"):
                    msg_id = data["result"]["message_id"]
                    return ToolResult(
                        output=f"Photo sent successfully (message_id: {msg_id})",
                        metadata={"message_id": msg_id, "chat_id": resolved},
                    )
                else:
                    return ToolResult(
                        success=False,
                        error=f"Telegram API error: {data.get('description', 'Unknown error')}",
                    )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class SendTelegramMediaGroupTool(BaseTool):
    name = "send_telegram_media_group"
    description = "Send multiple photos as an album to a Telegram chat. chat_id can be a numeric chat ID or the name of a Telegram credential to resolve. Max 10 photos per group."
    parameters_schema = {
        "type": "object",
        "properties": {
            "chat_id": {
                "type": "string",
                "description": "Numeric Telegram chat ID, or the name of a Telegram credential.",
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
        "required": ["chat_id", "photo_urls"],
    }

    async def execute(self, chat_id: str, photo_urls: list[str], caption: str = "", credential_values: dict[str, str] | None = None, **kwargs: Any) -> ToolResult:
        token = settings.telegram_bot_token
        if not token or token == "your-telegram-bot-token-here":
            return ToolResult(success=False, error="Telegram bot token not configured")

        if not photo_urls:
            return ToolResult(success=False, error="No photo URLs provided")

        resolved = _resolve_chat_id(chat_id, credential_values)
        if not resolved:
            return ToolResult(success=False, error=f"Could not resolve chat_id '{chat_id}' — not numeric and not a known credential.")

        urls = photo_urls[:10]
        media = []
        for i, url in enumerate(urls):
            item: dict = {"type": "photo", "media": url}
            if i == 0 and caption:
                item["caption"] = caption[:1024]
                item["parse_mode"] = "Markdown"
            media.append(item)

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(
                    f"https://api.telegram.org/bot{token}/sendMediaGroup",
                    json={"chat_id": resolved, "media": media},
                )
                data = resp.json()
                if data.get("ok"):
                    count = len(data["result"])
                    return ToolResult(
                        output=f"Album sent successfully ({count} photos)",
                        metadata={"chat_id": resolved, "photo_count": count},
                    )
                else:
                    return ToolResult(
                        success=False,
                        error=f"Telegram API error: {data.get('description', 'Unknown error')}",
                    )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
