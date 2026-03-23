"""Memory service — embeddings, storage, and semantic search via pgvector."""
import structlog
from openai import AsyncOpenAI
from sqlalchemy import delete, select, text
from uuid import UUID

from app.config import settings
from app.dependencies import async_session
from app.models.memory import Memory

logger = structlog.get_logger("memory")

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536

_openai_client: AsyncOpenAI | None = None


def _get_openai() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _openai_client


async def create_embedding(text_content: str) -> list[float]:
    """Generate an embedding vector for the given text."""
    client = _get_openai()
    response = await client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text_content,
        dimensions=EMBEDDING_DIMENSIONS,
    )
    return response.data[0].embedding


async def store_memory(
    content: str,
    agent_id: UUID | None = None,
    source: str = "conversation",
    source_id: str | None = None,
    summary: str | None = None,
    metadata: dict | None = None,
) -> Memory:
    """Store a new memory with its embedding."""
    embedding = await create_embedding(content)

    async with async_session() as db:
        memory = Memory(
            agent_id=agent_id,
            content=content,
            summary=summary,
            source=source,
            source_id=source_id,
            embedding=embedding,
            metadata_=metadata or {},
        )
        db.add(memory)
        await db.commit()
        await db.refresh(memory)

    await logger.ainfo("memory_stored", memory_id=str(memory.id), source=source)
    return memory


async def search_memories(
    query: str,
    agent_id: UUID | None = None,
    limit: int = 5,
    similarity_threshold: float = 0.3,
) -> list[tuple[Memory, float]]:
    """Semantic search over memories. Returns (memory, similarity_score) pairs."""
    query_embedding = await create_embedding(query)

    async with async_session() as db:
        # Use cosine distance: 1 - distance = similarity
        distance_expr = Memory.embedding.cosine_distance(query_embedding)

        stmt = (
            select(Memory, (1 - distance_expr).label("similarity"))
            .where((1 - distance_expr) >= similarity_threshold)
        )

        if agent_id is not None:
            stmt = stmt.where(
                (Memory.agent_id == agent_id) | (Memory.agent_id.is_(None))
            )

        stmt = stmt.order_by(distance_expr).limit(limit)

        result = await db.execute(stmt)
        rows = result.all()

    return [(row[0], float(row[1])) for row in rows]


async def get_relevant_context(
    query: str,
    agent_id: UUID | None = None,
    limit: int = 5,
) -> str:
    """Retrieve relevant memories and format as context string for injection into system prompt.

    Returns empty string if no memories are found (lazy RAG).
    """
    # Quick check: does this agent have any memories?
    async with async_session() as db:
        count_stmt = select(text("1")).select_from(Memory.__table__)
        if agent_id is not None:
            count_stmt = count_stmt.where(
                (Memory.agent_id == agent_id) | (Memory.agent_id.is_(None))
            )
        count_stmt = count_stmt.limit(1)
        result = await db.execute(count_stmt)
        if not result.first():
            return ""

    results = await search_memories(query, agent_id=agent_id, limit=limit)
    if not results:
        return ""

    lines = ["## Relevant Memories"]
    for memory, score in results:
        lines.append(f"- [{score:.2f}] {memory.content}")

    return "\n".join(lines)


async def delete_memory(memory_id: UUID) -> bool:
    """Delete a memory by ID."""
    async with async_session() as db:
        result = await db.execute(delete(Memory).where(Memory.id == memory_id))
        await db.commit()
        return result.rowcount > 0


async def list_memories(
    agent_id: UUID | None = None,
    source: str | None = None,
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[Memory], int]:
    """List memories with optional filters."""
    async with async_session() as db:
        stmt = select(Memory).order_by(Memory.created_at.desc())

        if agent_id is not None:
            stmt = stmt.where(Memory.agent_id == agent_id)
        if source is not None:
            stmt = stmt.where(Memory.source == source)

        # Count
        from sqlalchemy import func
        count_stmt = select(func.count(Memory.id))
        if agent_id is not None:
            count_stmt = count_stmt.where(Memory.agent_id == agent_id)
        if source is not None:
            count_stmt = count_stmt.where(Memory.source == source)
        total = (await db.execute(count_stmt)).scalar() or 0

        stmt = stmt.offset(offset).limit(limit)
        result = await db.execute(stmt)
        memories = list(result.scalars().all())

    return memories, total
