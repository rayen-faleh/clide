"""Tests for the conversation store."""

from __future__ import annotations

from pathlib import Path

import pytest

from clide.core.conversation_store import ConversationStore


@pytest.fixture
def store(tmp_path: Path) -> ConversationStore:
    return ConversationStore(db_path=tmp_path / "test.db")


class TestConversationStore:
    async def test_add_and_get_recent(self, store: ConversationStore) -> None:
        await store.add_message("user", "hello")
        await store.add_message("assistant", "hi there")
        messages = await store.get_recent()
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "hello"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"] == "hi there"

    async def test_get_recent_ordering(self, store: ConversationStore) -> None:
        """Messages should be returned in chronological order (oldest first)."""
        await store.add_message("user", "first")
        await store.add_message("assistant", "second")
        await store.add_message("user", "third")
        messages = await store.get_recent()
        contents = [m["content"] for m in messages]
        assert contents == ["first", "second", "third"]

    async def test_get_recent_limit(self, store: ConversationStore) -> None:
        for i in range(10):
            await store.add_message("user", f"msg {i}")
        messages = await store.get_recent(limit=3)
        assert len(messages) == 3
        # Should be the 3 most recent, in chronological order
        assert messages[0]["content"] == "msg 7"
        assert messages[1]["content"] == "msg 8"
        assert messages[2]["content"] == "msg 9"

    async def test_get_for_llm_format(self, store: ConversationStore) -> None:
        """get_for_llm should return only role and content."""
        await store.add_message("user", "hello")
        await store.add_message("assistant", "hi")
        messages = await store.get_for_llm()
        assert len(messages) == 2
        for msg in messages:
            assert set(msg.keys()) == {"role", "content"}
        assert messages[0] == {"role": "user", "content": "hello"}
        assert messages[1] == {"role": "assistant", "content": "hi"}

    async def test_clear(self, store: ConversationStore) -> None:
        await store.add_message("user", "hello")
        await store.clear()
        messages = await store.get_recent()
        assert messages == []

    async def test_empty_store_returns_empty_list(self, store: ConversationStore) -> None:
        messages = await store.get_recent()
        assert messages == []

    async def test_add_message_returns_id(self, store: ConversationStore) -> None:
        msg_id = await store.add_message("user", "hello")
        assert isinstance(msg_id, str)
        assert len(msg_id) > 0

    async def test_messages_have_created_at(self, store: ConversationStore) -> None:
        await store.add_message("user", "hello")
        messages = await store.get_recent()
        assert "created_at" in messages[0]
        assert len(messages[0]["created_at"]) > 0
