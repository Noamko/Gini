"""Seed built-in tools into the database."""
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models.tool import Tool
from app.tools.registry import BUILTIN_TOOLS


async def seed():
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        for tool_impl in BUILTIN_TOOLS:
            result = await session.execute(select(Tool).where(Tool.name == tool_impl.name))
            existing = result.scalar_one_or_none()

            if existing:
                # Update existing tool
                existing.description = tool_impl.description
                existing.parameters_schema = tool_impl.parameters_schema
                existing.implementation = f"app.tools.{tool_impl.name}.{type(tool_impl).__name__}"
                existing.requires_sandbox = tool_impl.requires_sandbox
                existing.requires_approval = tool_impl.requires_approval
                print(f"Updated tool: {tool_impl.name}")
            else:
                tool = Tool(
                    name=tool_impl.name,
                    description=tool_impl.description,
                    parameters_schema=tool_impl.parameters_schema,
                    implementation=f"app.tools.{tool_impl.name}.{type(tool_impl).__name__}",
                    requires_sandbox=tool_impl.requires_sandbox,
                    requires_approval=tool_impl.requires_approval,
                    is_builtin=True,
                )
                session.add(tool)
                print(f"Created tool: {tool_impl.name}")

        await session.commit()

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
