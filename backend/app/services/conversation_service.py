from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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
    await db.commit()
    await db.refresh(msg)
    return msg
