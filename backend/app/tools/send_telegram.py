from typing import Any

import httpx

from app.config import settings
from app.tools.base import BaseTool, ToolResult


class SendTelegramTool(BaseTool):
    name = "send_telegram"
    description = "Send a text message to a Telegram chat using the Gini bot."
    parameters_schema = {
        "type": "object",
        "properties": {
            "chat_id": {
                "type": "string",
                "description": "The Telegram chat ID to send the message to.",
            },
            "text": {
                "type": "string",
                "description": "The message text to send.",
            },
        },
        "required": ["chat_id", "text"],
    }

    async def execute(self, chat_id: str, text: str, **kwargs: Any) -> ToolResult:
        token = settings.telegram_bot_token
        if not token or token == "your-telegram-bot-token-here":
            return ToolResult(success=False, error="Telegram bot token not configured")

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
                )
                data = resp.json()
                if data.get("ok"):
                    msg_id = data["result"]["message_id"]
                    return ToolResult(
                        output=f"Message sent successfully (message_id: {msg_id})",
                        metadata={"message_id": msg_id, "chat_id": chat_id},
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
    description = "Send a photo to a Telegram chat by URL. Can include a caption."
    parameters_schema = {
        "type": "object",
        "properties": {
            "chat_id": {
                "type": "string",
                "description": "The Telegram chat ID to send the photo to.",
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

    async def execute(self, chat_id: str, photo_url: str, caption: str = "", **kwargs: Any) -> ToolResult:
        token = settings.telegram_bot_token
        if not token or token == "your-telegram-bot-token-here":
            return ToolResult(success=False, error="Telegram bot token not configured")

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                payload: dict = {"chat_id": chat_id, "photo": photo_url}
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
                        metadata={"message_id": msg_id, "chat_id": chat_id},
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
    description = "Send multiple photos as an album to a Telegram chat. Max 10 photos per group."
    parameters_schema = {
        "type": "object",
        "properties": {
            "chat_id": {
                "type": "string",
                "description": "The Telegram chat ID.",
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

    async def execute(self, chat_id: str, photo_urls: list[str], caption: str = "", **kwargs: Any) -> ToolResult:
        token = settings.telegram_bot_token
        if not token or token == "your-telegram-bot-token-here":
            return ToolResult(success=False, error="Telegram bot token not configured")

        if not photo_urls:
            return ToolResult(success=False, error="No photo URLs provided")

        urls = photo_urls[:10]
        media = []
        for i, url in enumerate(urls):
            item: dict = {"type": "photo", "media": url}
            if i == 0 and caption:
                item["caption"] = caption[:1024]
                item["parse_mode"] = "Markdown"
            media.append(item)

        try:
            import json
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(
                    f"https://api.telegram.org/bot{token}/sendMediaGroup",
                    json={"chat_id": chat_id, "media": media},
                )
                data = resp.json()
                if data.get("ok"):
                    count = len(data["result"])
                    return ToolResult(
                        output=f"Album sent successfully ({count} photos)",
                        metadata={"chat_id": chat_id, "photo_count": count},
                    )
                else:
                    return ToolResult(
                        success=False,
                        error=f"Telegram API error: {data.get('description', 'Unknown error')}",
                    )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
