"""Skill context injection into agent system prompts."""
import json
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import async_session, redis_client
from app.models.agent import Agent
from app.models.skill import Skill, agent_skills
from app.services.credential_vault import decrypt_value

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


def build_skill_context(skills: list[Skill], inject_credentials: bool = False, decrypted_creds: dict[str, str] | None = None) -> str:
    """Build a text block describing available skills for the system prompt.

    Args:
        skills: List of skills to include.
        inject_credentials: If True, inject actual credential values (for background runs).
        decrypted_creds: Map of credential name -> decrypted value.
    """
    if not skills:
        return ""

    lines = ["\n\n## Assigned Skills (MANDATORY)\n"]
    lines.append("You MUST use the following skills when performing related tasks.")
    lines.append("Follow each skill's instructions exactly. Do NOT use alternative approaches.\n")
    for skill in skills:
        lines.append(f"### SKILL: {skill.name}")
        if skill.description:
            lines.append(f"Purpose: {skill.description}")
        if skill.instructions:
            lines.append(f"REQUIRED approach:\n{skill.instructions}")
        if skill.tools:
            tool_names = [t.name for t in skill.tools]
            lines.append(f"Required tools: {', '.join(tool_names)}")
        if skill.credentials:
            if inject_credentials and decrypted_creds:
                lines.append("Credentials (use these exact values):")
                for c in skill.credentials:
                    val = decrypted_creds.get(c.name)
                    if val:
                        lines.append(f"  - {c.name} ({c.credential_type}): {val}")
                    else:
                        lines.append(f"  - {c.name} ({c.credential_type}): [not available]")
            else:
                cred_names = [c.name for c in skill.credentials]
                lines.append(f"Available credentials: {', '.join(cred_names)}")
        lines.append("")

    return "\n".join(lines)


async def get_assembled_prompt(agent: Agent) -> str:
    """Get the assembled system prompt with skill context, cached in Redis."""
    cache_key = f"{PROMPT_CACHE_PREFIX}{agent.id}"

    # Try cache first
    cached = await redis_client.get(cache_key)
    if cached:
        return cached

    # Build prompt
    skills = await get_agent_skills(agent.id)
    skill_context = build_skill_context(skills)
    full_prompt = agent.system_prompt + skill_context

    # Cache it
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


async def get_assembled_prompt_with_credentials(agent: Agent) -> str:
    """Get assembled prompt with decrypted credential values injected. For background runs only."""
    skills = await get_agent_skills(agent.id)
    if not skills:
        return agent.system_prompt + AUTONOMOUS_DIRECTIVE

    # Decrypt all credentials from assigned skills
    decrypted: dict[str, str] = {}
    for skill in skills:
        for c in skill.credentials:
            if c.is_active and c.name not in decrypted:
                try:
                    decrypted[c.name] = decrypt_value(c.encrypted_value)
                except Exception as e:
                    await logger.aerror("credential_decrypt_error", credential=c.name, error=str(e))

    skill_context = build_skill_context(skills, inject_credentials=True, decrypted_creds=decrypted)
    return agent.system_prompt + skill_context + AUTONOMOUS_DIRECTIVE


async def invalidate_prompt_cache(agent_id: UUID) -> None:
    """Invalidate the cached prompt for an agent (call on config change)."""
    cache_key = f"{PROMPT_CACHE_PREFIX}{agent_id}"
    await redis_client.delete(cache_key)


async def get_skill_credentials(skill_id: UUID) -> dict[str, str]:
    """Get decrypted credentials for a skill, keyed by credential name."""
    async with async_session() as db:
        skill = await db.get(Skill, skill_id)
        if not skill:
            return {}
        creds = {}
        for c in skill.credentials:
            if c.is_active:
                try:
                    creds[c.name] = decrypt_value(c.encrypted_value)
                except Exception as e:
                    await logger.aerror("credential_decrypt_error", credential=c.name, error=str(e))
        return creds
