"""Skill (playbook) context injection into agent system prompts.

Skills carry behavioral instructions only. Tools and credentials reach an agent through grants
(direct or skill-bundled) and are resolved/injected at execution time — see ``grant_resolver``.
"""

import re
from uuid import UUID

import structlog
from sqlalchemy import select

from app.dependencies import async_session, redis_client
from app.models.agent import Agent
from app.models.skill import Skill, agent_skills

logger = structlog.get_logger("skill_executor")

PROMPT_CACHE_PREFIX = "gini:prompt:"
PROMPT_CACHE_TTL = 300  # 5 minutes


async def get_agent_skills(agent_id: UUID) -> list[Skill]:
    """Load all active skills assigned to an agent."""
    async with async_session() as db:
        result = await db.execute(
            select(Skill)
            .join(agent_skills, Skill.id == agent_skills.c.skill_id)
            .where(agent_skills.c.agent_id == agent_id)
            .where(Skill.is_active == True)
        )
        return list(result.scalars().all())


async def get_agent_skill_tool_names(agent_id: UUID) -> set[str]:
    """Return the set of tool names bundled by an agent's active skills."""
    skills = await get_agent_skills(agent_id)
    return {tool.name for skill in skills for tool in skill.tools if tool.is_active}


def credential_env_var_name(credential_name: str) -> str:
    """Map a credential/slot name to a stable environment variable name."""
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", credential_name).strip("_").upper()
    return f"GINI_CRED_{normalized or 'VALUE'}"


def build_skill_context(skills: list[Skill]) -> str:
    """Build a text block describing the agent's assigned skill playbooks for the system prompt."""
    if not skills:
        return ""

    lines = ["\n\n## Assigned Skills (MANDATORY)\n"]
    lines.append("You MUST follow these skill playbooks when performing related tasks.")
    lines.append("Follow each skill's instructions exactly. Do NOT use alternative approaches.\n")
    for skill in skills:
        lines.append(f"### SKILL: {skill.name}")
        if skill.description:
            lines.append(f"Purpose: {skill.description}")
        if skill.instructions:
            lines.append(f"REQUIRED approach:\n{skill.instructions}")
        lines.append("")

    return "\n".join(lines)


async def get_assembled_prompt(agent: Agent) -> str:
    """Get the assembled system prompt with skill context, cached in Redis."""
    cache_key = f"{PROMPT_CACHE_PREFIX}{agent.id}"

    cached = await redis_client.get(cache_key)
    if cached:
        return cached

    skills = await get_agent_skills(agent.id)
    skill_context = build_skill_context(skills)
    full_prompt = agent.system_prompt + skill_context

    await redis_client.setex(cache_key, PROMPT_CACHE_TTL, full_prompt)

    return full_prompt


AUTONOMOUS_DIRECTIVE = """

## Execution Rules
You are running autonomously without a human in the loop. Follow these rules strictly:
- NEVER ask questions or request clarification. Act with the information you have.
- If you are missing information, make your best guess or use defaults.
- If a task cannot be completed, explain what failed and why in your response.
- Execute all steps yourself using the tools available to you.
- Do not suggest manual steps for the user to do — do everything yourself.
- Be concise in your final response — report what you did and the result.
"""


async def get_autonomous_prompt(agent: Agent) -> str:
    """Get the prompt for autonomous execution."""
    return await get_assembled_prompt(agent) + AUTONOMOUS_DIRECTIVE


async def invalidate_prompt_cache(agent_id: UUID) -> None:
    """Invalidate the cached prompt for an agent (call on config change)."""
    cache_key = f"{PROMPT_CACHE_PREFIX}{agent_id}"
    await redis_client.delete(cache_key)
