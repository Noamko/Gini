"""Redis-backed event bus with DB persistence."""
import json
import uuid

import structlog
from redis.asyncio import Redis

from app.dependencies import async_session, redis_client
from app.models.event import Event

logger = structlog.get_logger("event_bus")

CHANNEL_PREFIX = "gini:events:"


class EventBus:
    """Publish/subscribe event bus backed by Redis pub/sub with DB persistence."""

    def __init__(self, redis: Redis):
        self._redis = redis

    async def publish(
        self,
        event_type: str,
        payload: dict | None = None,
        correlation_id: str | None = None,
        conversation_id: str | None = None,
        source: str | None = None,
    ) -> str:
        """Publish an event to Redis and persist to DB. Returns event ID."""
        event_id = str(uuid.uuid4())

        event_data = {
            "id": event_id,
            "event_type": event_type,
            "correlation_id": correlation_id,
            "conversation_id": conversation_id,
            "source": source,
            "payload": payload or {},
        }

        # Publish to Redis channel
        channel = f"{CHANNEL_PREFIX}{event_type}"
        await self._redis.publish(channel, json.dumps(event_data))

        # Persist to DB
        async with async_session() as db:
            db_event = Event(
                id=uuid.UUID(event_id),
                event_type=event_type,
                correlation_id=correlation_id,
                conversation_id=uuid.UUID(conversation_id) if conversation_id else None,
                source=source,
                payload=payload or {},
                status="created",
            )
            db.add(db_event)
            await db.commit()

        await logger.ainfo("event_published", event_type=event_type, event_id=event_id)
        return event_id

    async def update_event_status(self, event_id: str, status: str, result: dict | None = None) -> None:
        """Update the status and result of a persisted event."""
        async with async_session() as db:
            event = await db.get(Event, uuid.UUID(event_id))
            if event:
                event.status = status
                if result:
                    event.result = result
                await db.commit()


# Singleton
event_bus = EventBus(redis_client)
