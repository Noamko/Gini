"""Skill context injection into agent system prompts."""
import re
from uuid import UUID

import structlog
from sqlalchemy import select

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


async def get_agent_skill_tool_names(agent_id: UUID) -> set[str]:
    """Return the set of tool names explicitly linked through an agent's active skills."""
    skills = await get_agent_skills(agent_id)
    return {
        tool.name
        for skill in skills
        for tool in skill.tools
        if tool.is_active
    }


def credential_env_var_name(credential_name: str) -> str:
    """Map a credential name to a stable environment variable name."""
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", credential_name).strip("_").upper()
    return f"GINI_CRED_{normalized or 'VALUE'}"


async def get_agent_credentials(agent_id: UUID) -> dict[str, str]:
    """Return decrypted credentials for an agent, keyed by credential name."""
    skills = await get_agent_skills(agent_id)
    decrypted: dict[str, str] = {}
    for skill in skills:
        for credential in skill.credentials:
            if not credential.is_active or credential.name in decrypted:
                continue
            try:
                decrypted[credential.name] = decrypt_value(credential.encrypted_value)
            except Exception as e:
                await logger.aerror("credential_decrypt_error", credential=credential.name, error=str(e))
    return decrypted


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
            lines.append("Available credential handles:")
            for c in skill.credentials:
                env_name = credential_env_var_name(c.name)
                availability = ""
                if inject_credentials and decrypted_creds is not None and c.name not in decrypted_creds:
                    availability = " [not currently available]"
                lines.append(
                    f"  - {c.name} ({c.credential_type}) -> request by this exact name in tool arguments; "
                    f"for `run_shell` it will be exposed as ${env_name}{availability}."
                )
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
    """Deprecated compatibility wrapper.

    Secrets are no longer injected into prompts. They are delivered only at
    tool execution time.
    """
    return await get_assembled_prompt(agent) + AUTONOMOUS_DIRECTIVE


async def get_autonomous_prompt(agent: Agent) -> str:
    """Get the prompt for autonomous execution."""
    return await get_assembled_prompt(agent) + AUTONOMOUS_DIRECTIVE


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
