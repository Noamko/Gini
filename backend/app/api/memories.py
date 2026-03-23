"""Memory CRUD and search endpoints."""
from uuid import UUID

from fastapi import APIRouter, Query
from app.schemas.memory import MemoryCreate, MemoryResponse
from app.services.memory_service import (
    store_memory,
    search_memories,
    delete_memory,
    list_memories,
)

router = APIRouter(tags=["memories"])


@router.get("/api/memories")
async def get_memories(
    agent_id: UUID | None = None,
    source: str | None = None,
    q: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """List or search memories."""
    if q:
        # Semantic search
        results = await search_memories(query=q, agent_id=agent_id, limit=limit)
        items = [
            MemoryResponse(
                id=m.id,
                agent_id=m.agent_id,
                content=m.content,
                summary=m.summary,
                source=m.source,
                source_id=m.source_id,
                metadata=m.metadata_,
                similarity=score,
                created_at=m.created_at,
                updated_at=m.updated_at,
            )
            for m, score in results
        ]
        return {"items": items, "total": len(items), "offset": 0, "limit": limit}

    memories, total = await list_memories(
        agent_id=agent_id, source=source, offset=offset, limit=limit,
    )
    items = [
        MemoryResponse(
            id=m.id,
            agent_id=m.agent_id,
            content=m.content,
            summary=m.summary,
            source=m.source,
            source_id=m.source_id,
            metadata=m.metadata_,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )
        for m in memories
    ]
    return {"items": items, "total": total, "offset": offset, "limit": limit}


@router.post("/api/memories", status_code=201)
async def create_memory(body: MemoryCreate):
    """Store a new memory (generates embedding automatically)."""
    memory = await store_memory(
        content=body.content,
        agent_id=body.agent_id,
        source=body.source,
        source_id=body.source_id,
        metadata=body.metadata,
    )
    return MemoryResponse(
        id=memory.id,
        agent_id=memory.agent_id,
        content=memory.content,
        summary=memory.summary,
        source=memory.source,
        source_id=memory.source_id,
        metadata=memory.metadata_,
        created_at=memory.created_at,
        updated_at=memory.updated_at,
    )


@router.delete("/api/memories/{memory_id}", status_code=204)
async def remove_memory(memory_id: UUID):
    """Delete a memory."""
    await delete_memory(memory_id)
