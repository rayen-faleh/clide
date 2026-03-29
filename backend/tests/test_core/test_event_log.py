"""Tests for the event log."""

from __future__ import annotations

from pathlib import Path

import pytest

from clide.core.event_log import EventLog


@pytest.fixture
def log(tmp_path: Path) -> EventLog:
    return EventLog(db_path=tmp_path / "test_events.db")


class TestEventLog:
    async def test_append_and_get_session(self, log: EventLog) -> None:
        """Append 3 events, verify get_session returns them in ASC order."""
        await log.append("sess1", "chat", "user_message", role="user", content="hello")
        await log.append("sess1", "chat", "assistant_message", role="assistant", content="hi")
        await log.append("sess1", "chat", "tool_call", content="tool_data")
        events = await log.get_session("sess1")
        assert len(events) == 3
        assert events[0]["event_type"] == "user_message"
        assert events[1]["event_type"] == "assistant_message"
        assert events[2]["event_type"] == "tool_call"

    async def test_append_returns_event_id(self, log: EventLog) -> None:
        """append() returns a non-empty string UUID."""
        event_id = await log.append("sess1", "chat", "user_message", role="user", content="hello")
        assert isinstance(event_id, str)
        assert len(event_id) > 0

    async def test_get_recent_no_filter(self, log: EventLog) -> None:
        """Append 5 events across 2 modes, verify DESC ordering and count."""
        await log.append("sess1", "chat", "user_message", role="user", content="msg1")
        await log.append("sess1", "chat", "user_message", role="user", content="msg2")
        await log.append("sess1", "chat", "user_message", role="user", content="msg3")
        await log.append("sess2", "thinking", "thought", content="think1")
        await log.append("sess2", "thinking", "thought", content="think2")
        events = await log.get_recent()
        assert len(events) == 5
        # DESC order — most recent first
        assert events[0]["content"] == "think2"

    async def test_get_recent_filter_by_mode(self, log: EventLog) -> None:
        """Append chat + thinking events, filter by mode=chat returns only chat."""
        await log.append("sess1", "chat", "user_message", role="user", content="chat_msg")
        await log.append("sess1", "thinking", "thought", content="thought_msg")
        events = await log.get_recent(mode="chat")
        assert len(events) == 1
        assert events[0]["mode"] == "chat"
        assert events[0]["content"] == "chat_msg"

    async def test_get_recent_filter_by_event_type(self, log: EventLog) -> None:
        """Filter by event_type=tool_call."""
        await log.append("sess1", "chat", "user_message", role="user", content="hello")
        await log.append("sess1", "chat", "tool_call", content="tool_data")
        await log.append("sess1", "chat", "tool_call", content="tool_data2")
        events = await log.get_recent(event_type="tool_call")
        assert len(events) == 2
        for e in events:
            assert e["event_type"] == "tool_call"

    async def test_get_recent_respects_limit(self, log: EventLog) -> None:
        """Append 10 events, limit=3 returns only 3."""
        for i in range(10):
            await log.append("sess1", "chat", "user_message", role="user", content=f"msg{i}")
        events = await log.get_recent(limit=3)
        assert len(events) == 3

    async def test_get_for_llm_context_only_messages(self, log: EventLog) -> None:
        """Append user_message, assistant_message, tool_call — only first two in LLM context."""
        await log.append("sess1", "chat", "user_message", role="user", content="hello")
        await log.append("sess1", "chat", "assistant_message", role="assistant", content="hi")
        await log.append("sess1", "chat", "tool_call", content="tool_data")
        messages = await log.get_for_llm_context()
        assert len(messages) == 2
        roles = [m["role"] for m in messages]
        assert "user" in roles
        assert "assistant" in roles

    async def test_get_for_llm_context_mode_filter(self, log: EventLog) -> None:
        """thinking events excluded when modes=["chat"]."""
        await log.append("sess1", "chat", "user_message", role="user", content="chat_msg")
        await log.append("sess1", "thinking", "user_message", role="user", content="think_msg")
        messages = await log.get_for_llm_context(modes=["chat"])
        assert len(messages) == 1
        assert messages[0]["content"] == "chat_msg"

    async def test_get_for_llm_context_chronological_order(self, log: EventLog) -> None:
        """Results are in chronological (ASC) order."""
        await log.append("sess1", "chat", "user_message", role="user", content="first")
        await log.append("sess1", "chat", "assistant_message", role="assistant", content="second")
        await log.append("sess1", "chat", "user_message", role="user", content="third")
        messages = await log.get_for_llm_context()
        contents = [m["content"] for m in messages]
        assert contents == ["first", "second", "third"]

    async def test_get_for_llm_context_default_mode_is_chat(self, log: EventLog) -> None:
        """When modes=None, defaults to ["chat"] only."""
        await log.append("sess1", "chat", "user_message", role="user", content="chat_msg")
        await log.append("sess1", "thinking", "user_message", role="user", content="think_msg")
        messages = await log.get_for_llm_context(modes=None)
        assert len(messages) == 1
        assert messages[0]["content"] == "chat_msg"

    async def test_get_recent_by_type(self, log: EventLog) -> None:
        """Filter by specific event type."""
        await log.append("sess1", "chat", "user_message", role="user", content="hello")
        await log.append("sess1", "chat", "tool_call", content="tool1")
        await log.append("sess1", "chat", "tool_call", content="tool2")
        events = await log.get_recent_by_type("tool_call")
        assert len(events) == 2
        for e in events:
            assert e["event_type"] == "tool_call"

    async def test_metadata_roundtrip(self, log: EventLog) -> None:
        """Dict metadata is serialized and deserialized correctly."""
        meta = {"key": "value", "count": 42, "nested": {"a": 1}}
        await log.append("sess1", "chat", "user_message", metadata=meta)
        events = await log.get_session("sess1")
        assert events[0]["metadata"] == meta

    async def test_metadata_default_empty_dict(self, log: EventLog) -> None:
        """When no metadata passed, it defaults to {}."""
        await log.append("sess1", "chat", "user_message")
        events = await log.get_session("sess1")
        assert events[0]["metadata"] == {}

    async def test_get_session_returns_only_matching_session(self, log: EventLog) -> None:
        """get_session only returns events for the requested session_id."""
        await log.append("sess1", "chat", "user_message", content="sess1_msg")
        await log.append("sess2", "chat", "user_message", content="sess2_msg")
        events = await log.get_session("sess1")
        assert len(events) == 1
        assert events[0]["content"] == "sess1_msg"

    async def test_get_session_empty_for_unknown_session(self, log: EventLog) -> None:
        """get_session returns [] for a session with no events."""
        await log.append("sess1", "chat", "user_message", content="hello")
        events = await log.get_session("unknown_session")
        assert events == []
