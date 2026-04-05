"""Tests for conversation persistence helpers."""
from datetime import UTC, datetime

from sqlalchemy import update

from app.models.agent import Agent
from app.models.conversation import Conversation
from app.models.message import Message
from app.services import conversation_service


async def test_create_message_touches_conversation_timestamp(db_session):
    conv = await conversation_service.create_conversation(db_session, title="timestamp test")
    old_time = datetime(2020, 1, 1, tzinfo=UTC)
    await db_session.execute(
        update(Conversation).where(Conversation.id == conv.id).values(updated_at=old_time)
    )
    await db_session.commit()

    msg = await conversation_service.create_message(
        db_session,
        conversation_id=conv.id,
        role="user",
        content="hello",
    )

    refreshed = await conversation_service.get_conversation(db_session, conv.id)
    assert msg.conversation_id == conv.id
    assert refreshed is not None
    assert refreshed.updated_at > old_time


async def test_build_llm_history_reconstructs_tool_rounds():
    history = conversation_service.build_llm_history([
        Message(role="user", content="find listings"),
        Message(
            role="assistant",
            content="I will search.",
            tool_calls=[{"id": "tool-1", "name": "search", "input": {"q": "listing"}}],
        ),
        Message(role="tool", content='{"items":[1]}', tool_call_id="tool-1"),
        Message(role="assistant", content="Found one result."),
    ])

    assert history == [
        {"role": "user", "content": "find listings"},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "I will search."},
                {"type": "tool_use", "id": "tool-1", "name": "search", "input": {"q": "listing"}},
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "tool-1", "content": '{"items":[1]}'},
            ],
        },
        {"role": "assistant", "content": "Found one result."},
    ]


async def test_get_conversation_agent_and_history_uses_main_agent_when_conversation_has_none(db_session):
    agent = Agent(
        name="Main",
        system_prompt="You are main.",
        llm_provider="openai",
        llm_model="gpt-4o-mini",
        is_main=True,
    )
    db_session.add(agent)
    await db_session.commit()

    conv = await conversation_service.create_conversation(db_session, title="history test")
    await conversation_service.create_message(
        db_session,
        conversation_id=conv.id,
        role="user",
        content="hello",
    )

    loaded_conv, loaded_agent, history = await conversation_service.get_conversation_agent_and_history(
        db_session,
        conv.id,
    )

    assert loaded_conv is not None
    assert loaded_conv.id == conv.id
    assert loaded_agent is not None
    assert loaded_agent.id == agent.id
    assert history == [{"role": "user", "content": "hello"}]
