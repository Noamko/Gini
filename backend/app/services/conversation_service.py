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
    """Rebuild structured LLM history from persisted conversation messages.

    Incomplete tool rounds are sanitized so a failed or interrupted tool call
    does not leave invalid history for later retries.
    """
    messages: list[dict] = []
    pending_tool_round: dict | None = None

    def flush_tool_round() -> None:
        nonlocal pending_tool_round
        if not pending_tool_round:
            return

        matched_tool_results = list(pending_tool_round["tool_results"])
        matched_tool_ids = {
            result["tool_use_id"]
            for result in matched_tool_results
            if result.get("tool_use_id")
        }

        if matched_tool_results:
            assistant_content = []
            if pending_tool_round["text"]:
                assistant_content.append({"type": "text", "text": pending_tool_round["text"]})

            for tool_call in pending_tool_round["tool_calls"]:
                tool_call_id = tool_call.get("id", "")
                if tool_call_id and tool_call_id in matched_tool_ids:
                    assistant_content.append({
                        "type": "tool_use",
                        "id": tool_call_id,
                        "name": tool_call.get("name", ""),
                        "input": tool_call.get("input", {}),
                    })

            if assistant_content:
                messages.append({"role": "assistant", "content": assistant_content})
            messages.append({"role": "user", "content": matched_tool_results})
        elif pending_tool_round["text"]:
            messages.append({"role": "assistant", "content": pending_tool_round["text"]})

        pending_tool_round = None

    for message in db_messages:
        if message.role == "tool":
            if pending_tool_round and message.tool_call_id in pending_tool_round["tool_call_ids"]:
                pending_tool_round["tool_results"].append({
                    "type": "tool_result",
                    "tool_use_id": message.tool_call_id or "",
                    "content": message.content or "",
                })
            continue

        flush_tool_round()

        if message.role == "assistant" and message.tool_calls:
            raw_tool_calls = message.tool_calls if isinstance(message.tool_calls, list) else [message.tool_calls]
            normalized_tool_calls = [
                tool_call
                for tool_call in raw_tool_calls
                if isinstance(tool_call, dict) and tool_call.get("id")
            ]
            if normalized_tool_calls:
                pending_tool_round = {
                    "text": message.content or "",
                    "tool_calls": normalized_tool_calls,
                    "tool_call_ids": {tool_call["id"] for tool_call in normalized_tool_calls},
                    "tool_results": [],
                }
                continue

        if message.role in ("user", "assistant"):
            messages.append({"role": message.role, "content": message.content or ""})

    flush_tool_round()
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
