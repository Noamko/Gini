"""Meta-tool: let an agent create an inbound trigger webhook."""

from typing import Any

import structlog
from fastapi import HTTPException

from app.config import settings
from app.dependencies import async_session
from app.tools.base import BaseTool, ToolResult

logger = structlog.get_logger("create_webhook")


class CreateWebhookTool(BaseTool):
    name = "create_webhook"
    description = (
        "Create an inbound webhook bound to an agent. External systems POST JSON to the returned URL to "
        "start an agent run; the payload (plus the optional instructions_template) becomes the run's "
        "instructions. If agent_id is omitted, the webhook is bound to the calling agent. Returns the "
        "public trigger URL and a secret token — share the URL only with trusted callers."
    )
    requires_sandbox = False
    requires_approval = True
    default_catalog = False
    parameters_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Webhook name."},
            "agent_id": {
                "type": "string",
                "description": "Agent id to trigger. Omit to bind to the calling agent.",
            },
            "instructions_template": {
                "type": "string",
                "description": "Optional text prepended to the payload to instruct the agent on each trigger.",
            },
            "enabled": {
                "type": "boolean",
                "description": "Whether the webhook is active. Default true.",
            },
        },
        "required": ["name"],
    }

    async def execute(self, *, caller_agent_id: str | None = None, **kwargs: Any) -> ToolResult:
        from app.schemas.webhook import WebhookCreate

        kwargs.pop("credential_values", None)
        agent_id = kwargs.get("agent_id") or caller_agent_id
        if not agent_id:
            return ToolResult(
                success=False,
                error="No agent_id provided and there is no calling agent to default to.",
            )

        try:
            body = WebhookCreate(
                agent_id=str(agent_id),
                name=kwargs.get("name", ""),
                instructions_template=kwargs.get("instructions_template"),
                enabled=bool(kwargs.get("enabled", True)),
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Invalid webhook parameters: {e}")

        from app.api.webhooks import create_webhook as create_webhook_endpoint

        try:
            async with async_session() as db:
                resp = await create_webhook_endpoint(body, db=db)
        except HTTPException as e:
            return ToolResult(success=False, error=f"{e.status_code}: {e.detail}")
        except Exception as e:
            await logger.aerror("create_webhook_failed", error=str(e))
            return ToolResult(success=False, error=f"create_webhook failed: {e}")

        url = f"{settings.public_base_url.rstrip('/')}/api/webhooks/{resp.token}/trigger"
        await logger.ainfo("webhook_created", webhook_id=str(resp.id), name=resp.name, by=caller_agent_id)
        return ToolResult(
            output=(
                f"Created webhook '{resp.name}' for agent {resp.agent_name}.\n"
                f"Trigger URL: {url}\n"
                f"POST any JSON body to this URL to start a run."
            ),
            metadata={"webhook_id": str(resp.id), "url": url, "token": resp.token},
        )
