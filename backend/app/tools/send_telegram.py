from typing import Any

import httpx

from app.config import settings
from app.tools.base import BaseTool, ToolResult


class SendTelegramTool(BaseTool):
    name = "send_telegram"
    description = "Send a message to a Telegram chat using the Gini bot. Requires a chat_id and message text."
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
