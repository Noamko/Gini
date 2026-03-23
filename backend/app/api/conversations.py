from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.schemas.conversation import ConversationCreate, ConversationResponse
from app.schemas.message import MessageResponse
from app.services import conversation_service

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("")
async def list_conversations(
    offset: int = 0, limit: int = 20, db: AsyncSession = Depends(get_db)
):
    conversations, total = await conversation_service.list_conversations(db, offset, limit)
    return {
        "items": [ConversationResponse.from_orm_model(c) for c in conversations],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.post("", status_code=201)
async def create_conversation(
    body: ConversationCreate, db: AsyncSession = Depends(get_db)
):
    conv = await conversation_service.create_conversation(
        db, title=body.title, agent_id=body.agent_id, metadata=body.metadata
    )
    return ConversationResponse.from_orm_model(conv)


@router.get("/{conversation_id}")
async def get_conversation(conversation_id: UUID, db: AsyncSession = Depends(get_db)):
    conv = await conversation_service.get_conversation(db, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return ConversationResponse.from_orm_model(conv)


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: UUID, db: AsyncSession = Depends(get_db)):
    deleted = await conversation_service.delete_conversation(db, conversation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")


@router.get("/{conversation_id}/messages")
async def list_messages(
    conversation_id: UUID, offset: int = 0, limit: int = 50, db: AsyncSession = Depends(get_db)
):
    messages, total = await conversation_service.list_messages(db, conversation_id, offset, limit)
    return {
        "items": [MessageResponse.from_orm_model(m) for m in messages],
        "total": total,
        "offset": offset,
        "limit": limit,
    }
