from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.agent import Agent
from app.models.conversation import Conversation
from app.models.message import Message


async def list_conversations(
    db: AsyncSession, offset: int = 0, limit: int = 20
) -> tuple[list[Conversation], int]:
    count_result = await db.execute(select(func.count(Conversation.id)))
    total = count_result.scalar_one()

    result = await db.execute(
        select(Conversation)
        .order_by(Conversation.updated_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return result.scalars().all(), total


async def get_conversation(db: AsyncSession, conversation_id: UUID) -> Conversation | None:
    result = await db.execute(
        select(Conversation)
        .where(Conversation.id == conversation_id)
        .options(selectinload(Conversation.messages))
    )
    return result.scalar_one_or_none()


def build_llm_history(db_messages: list[Message]) -> list[dict]:
    """Rebuild structured LLM history from persisted conversation messages."""
    messages: list[dict] = []
    pending_tool_results: list[dict] = []

    def flush_tool_results() -> None:
        if pending_tool_results:
            messages.append({"role": "user", "content": list(pending_tool_results)})
            pending_tool_results.clear()

    for message in db_messages:
        if message.role == "tool":
            pending_tool_results.append({
                "type": "tool_result",
                "tool_use_id": message.tool_call_id or "",
                "content": message.content or "",
            })
            continue

        flush_tool_results()

        if message.role == "assistant" and message.tool_calls:
            assistant_content = []
            if message.content:
                assistant_content.append({"type": "text", "text": message.content})

            raw_tool_calls = message.tool_calls if isinstance(message.tool_calls, list) else [message.tool_calls]
            for tool_call in raw_tool_calls:
                if not isinstance(tool_call, dict):
                    continue
                assistant_content.append({
                    "type": "tool_use",
                    "id": tool_call.get("id", ""),
                    "name": tool_call.get("name", ""),
                    "input": tool_call.get("input", {}),
                })

            if assistant_content:
                messages.append({"role": "assistant", "content": assistant_content})
        elif message.role in ("user", "assistant"):
            messages.append({"role": message.role, "content": message.content or ""})

    flush_tool_results()
    return messages


async def get_conversation_agent_and_history(
    db: AsyncSession,
    conversation_id: UUID,
) -> tuple[Conversation | None, Agent | None, list[dict]]:
    """Load a conversation, resolve its agent, and rebuild structured history."""
    conv = await db.get(Conversation, conversation_id)
    if not conv:
        return None, None, []

    if conv.agent_id:
        agent = await db.get(Agent, conv.agent_id)
    else:
        result = await db.execute(select(Agent).where(Agent.is_main == True))
        agent = result.scalar_one_or_none()

    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    )
    return conv, agent, build_llm_history(result.scalars().all())


async def create_conversation(db: AsyncSession, title: str | None = None, agent_id: UUID | None = None, metadata: dict | None = None) -> Conversation:
    conv = Conversation(title=title, agent_id=agent_id, metadata_=metadata or {})
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return conv


async def delete_conversation(db: AsyncSession, conversation_id: UUID) -> bool:
    conv = await db.get(Conversation, conversation_id)
    if not conv:
        return False
    await db.delete(conv)
    await db.commit()
    return True


async def list_messages(
    db: AsyncSession, conversation_id: UUID, offset: int = 0, limit: int = 50
) -> tuple[list[Message], int]:
    count_result = await db.execute(
        select(func.count(Message.id)).where(Message.conversation_id == conversation_id)
    )
    total = count_result.scalar_one()

    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
        .offset(offset)
        .limit(limit)
    )
    return result.scalars().all(), total


async def create_message(db: AsyncSession, conversation_id: UUID, **kwargs) -> Message:
    msg = Message(conversation_id=conversation_id, **kwargs)
    db.add(msg)
    await db.flush()
    await db.execute(
        update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(updated_at=func.now())
    )
    await db.commit()
    await db.refresh(msg)
    return msg
