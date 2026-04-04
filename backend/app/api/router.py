from fastapi import APIRouter

from app.api.agents import router as agents_router
from app.api.backup import router as backup_router
from app.api.chat import router as chat_router
from app.api.conversations import router as conversations_router
from app.api.credentials import router as credentials_router
from app.api.dashboard import router as dashboard_router
from app.api.events import router as events_router
from app.api.execution_logs import router as traces_router
from app.api.health import router as health_router
from app.api.models import router as models_router
from app.api.runs import router as runs_router
from app.api.schedules import router as schedules_router
from app.api.settings_api import router as settings_router
from app.api.skills import router as skills_router
from app.api.templates import router as templates_router
from app.api.tools import router as tools_router
from app.api.webhooks import router as webhooks_router
from app.api.workflows import router as workflows_router

root_router = APIRouter()
root_router.include_router(health_router)
root_router.include_router(conversations_router)
root_router.include_router(chat_router)
root_router.include_router(agents_router)
root_router.include_router(tools_router)
root_router.include_router(events_router)
root_router.include_router(skills_router)
root_router.include_router(credentials_router)
root_router.include_router(dashboard_router)
root_router.include_router(traces_router)
root_router.include_router(settings_router)
root_router.include_router(models_router)
root_router.include_router(runs_router)
root_router.include_router(schedules_router)
root_router.include_router(webhooks_router)
root_router.include_router(workflows_router)
root_router.include_router(templates_router)
root_router.include_router(backup_router)
