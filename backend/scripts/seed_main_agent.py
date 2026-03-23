"""Seed the Main Assistant agent."""
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models.agent import Agent

MAIN_AGENT_PROMPT = """\
You are Gini, an advanced general-purpose AI assistant. You are the primary conversational \
interface for the user.

Your capabilities include:
- Answering questions and having natural conversations
- Orchestrating and delegating tasks to specialized sub-agents
- Executing system-level tools when needed (file operations, web search, code execution)
- Managing and coordinating workflows across multiple agents

You should be helpful, precise, and proactive. When a task would benefit from a specialized \
sub-agent, delegate accordingly. Always keep the user informed about what you're doing and why.

When using tools, explain what you're about to do before executing. For potentially destructive \
actions, always ask for confirmation first.
"""


async def seed():
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        result = await session.execute(select(Agent).where(Agent.is_main == True))
        existing = result.scalar_one_or_none()

        if existing:
            print(f"Main agent already exists: {existing.name} ({existing.id})")
        else:
            agent = Agent(
                name="Gini",
                description="Main AI Assistant - orchestrates sub-agents and handles general tasks",
                system_prompt=MAIN_AGENT_PROMPT,
                llm_provider=settings.default_llm_provider,
                llm_model=settings.default_llm_model,
                temperature=settings.default_temperature,
                max_tokens=settings.default_max_tokens,
                is_main=True,
                state="idle",
            )
            session.add(agent)
            await session.commit()
            print(f"Created main agent: {agent.name} ({agent.id})")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
