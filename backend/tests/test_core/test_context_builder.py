"""Tests for the shared context builder."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from clide.core.context_builder import ContextBuilder, format_age
from clide.core.event_log import EventLog

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@dataclass
class FakeZettel:
    """Minimal stand-in for memory.models.Zettel."""

    id: str = "z1"
    content: str = "some content"
    summary: str = "short summary"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


def _make_event(
    mode: str = "chat",
    event_type: str = "user_message",
    content: str = "hello",
    metadata: dict[str, Any] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    return {
        "id": "evt-1",
        "session_id": "s1",
        "mode": mode,
        "event_type": event_type,
        "role": "user" if event_type == "user_message" else "assistant",
        "content": content,
        "metadata": metadata or {},
        "created_at": created_at or datetime.now(UTC).isoformat(),
    }


def _make_amem(zettels: list[FakeZettel] | None = None) -> Any:
    amem = MagicMock()
    amem.recall = AsyncMock(return_value=zettels or [])
    return amem


def _make_event_log(events_by_mode: dict[str, list[dict[str, Any]]] | None = None) -> Any:
    """Create a mock EventLog that returns events per mode."""
    log = MagicMock(spec=EventLog)
    events_by_mode = events_by_mode or {}

    async def _get_recent(
        limit: int = 50,
        mode: str | None = None,
        event_type: str | None = None,
    ) -> list[dict[str, Any]]:
        if mode is None:
            all_events: list[dict[str, Any]] = []
            for evts in events_by_mode.values():
                all_events.extend(evts)
            return all_events[:limit]
        return (events_by_mode.get(mode) or [])[:limit]

    log.get_recent = AsyncMock(side_effect=_get_recent)
    return log


# ---------------------------------------------------------------------------
# format_age
# ---------------------------------------------------------------------------

class TestFormatAge:
    def test_none_returns_unknown(self) -> None:
        assert format_age(None) == "unknown"

    def test_just_now(self) -> None:
        dt = datetime.now(UTC) - timedelta(seconds=5)
        assert format_age(dt) == "just now"

    def test_minutes(self) -> None:
        dt = datetime.now(UTC) - timedelta(minutes=15)
        assert format_age(dt) == "15m ago"

    def test_hours(self) -> None:
        dt = datetime.now(UTC) - timedelta(hours=3)
        assert format_age(dt) == "3h ago"

    def test_days(self) -> None:
        dt = datetime.now(UTC) - timedelta(days=7)
        assert format_age(dt) == "7d ago"

    def test_naive_datetime_treated_as_utc(self) -> None:
        dt = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=2)
        result = format_age(dt)
        assert "h ago" in result


# ---------------------------------------------------------------------------
# ContextBuilder.build
# ---------------------------------------------------------------------------

class TestBuildWithMemoriesOnly:
    @pytest.mark.asyncio
    async def test_returns_formatted_memories(self) -> None:
        zettels = [
            FakeZettel(id="z1", summary="learned about X"),
            FakeZettel(id="z2", summary="user prefers Y"),
            FakeZettel(id="z3", summary="workshop result Z"),
        ]
        amem = _make_amem(zettels)
        event_log = _make_event_log()

        builder = ContextBuilder(event_log=event_log, amem=amem)
        result = await builder.build(query="test", current_mode="chat")

        assert result.memories_used == 3
        assert "learned about X" in result.memory_text
        assert "user prefers Y" in result.memory_text
        assert "workshop result Z" in result.memory_text
        assert result.cross_mode_text == ""
        amem.recall.assert_awaited_once_with("test", limit=5)


class TestBuildWithEventsOnly:
    @pytest.mark.asyncio
    async def test_returns_cross_mode_events(self) -> None:
        events = {
            "thinking": [
                _make_event(mode="thinking", event_type="thought", content="I wonder about X"),
            ],
            "workshop": [
                _make_event(
                    mode="workshop", event_type="assistant_message",
                    content="Step completed",
                ),
            ],
        }
        event_log = _make_event_log(events)
        builder = ContextBuilder(event_log=event_log, amem=None)

        result = await builder.build(query="test", current_mode="chat")

        assert result.memories_used == 0
        assert result.memory_text == ""
        assert "[thinking] You reflected:" in result.cross_mode_text
        assert "[workshop] You said:" in result.cross_mode_text


class TestBuildWithBoth:
    @pytest.mark.asyncio
    async def test_both_memory_and_events(self) -> None:
        zettels = [FakeZettel(id="z1", summary="important fact")]
        events = {
            "workshop": [
                _make_event(mode="workshop", event_type="user_message", content="build X"),
            ],
        }
        amem = _make_amem(zettels)
        event_log = _make_event_log(events)
        builder = ContextBuilder(event_log=event_log, amem=amem)

        result = await builder.build(query="test", current_mode="chat")

        assert result.memories_used == 1
        assert "important fact" in result.memory_text
        assert "[workshop] User:" in result.cross_mode_text


class TestBuildExcludesCurrentMode:
    @pytest.mark.asyncio
    async def test_chat_events_excluded_when_current_is_chat(self) -> None:
        events = {
            "chat": [
                _make_event(mode="chat", event_type="user_message", content="should not appear"),
            ],
            "thinking": [
                _make_event(mode="thinking", event_type="thought", content="visible thought"),
            ],
        }
        event_log = _make_event_log(events)
        builder = ContextBuilder(event_log=event_log, amem=None)

        result = await builder.build(query="test", current_mode="chat")

        assert "should not appear" not in result.cross_mode_text
        assert "visible thought" in result.cross_mode_text


class TestBuildEmpty:
    @pytest.mark.asyncio
    async def test_empty_when_nothing_available(self) -> None:
        amem = _make_amem([])
        event_log = _make_event_log()
        builder = ContextBuilder(event_log=event_log, amem=amem)

        result = await builder.build(query="test", current_mode="chat")

        assert result.memory_text == ""
        assert result.cross_mode_text == ""
        assert result.memories_used == 0


class TestEventContentTruncation:
    @pytest.mark.asyncio
    async def test_long_content_truncated(self) -> None:
        long_content = "x" * 200
        events = {
            "thinking": [
                _make_event(mode="thinking", event_type="thought", content=long_content),
            ],
        }
        event_log = _make_event_log(events)
        builder = ContextBuilder(event_log=event_log, amem=None)

        result = await builder.build(query="test", current_mode="chat")

        # Content should be truncated to 120 chars + "..."
        for line in result.cross_mode_text.split("\n"):
            # Each line has prefix "- [thinking] You reflected: " then truncated content
            assert len(line) < 200


class TestCustomIncludeModes:
    @pytest.mark.asyncio
    async def test_explicit_include_modes(self) -> None:
        events = {
            "chat": [
                _make_event(mode="chat", event_type="user_message", content="chat msg"),
            ],
            "thinking": [
                _make_event(mode="thinking", event_type="thought", content="thought msg"),
            ],
            "workshop": [
                _make_event(
                    mode="workshop", event_type="assistant_message",
                    content="workshop msg",
                ),
            ],
        }
        event_log = _make_event_log(events)
        builder = ContextBuilder(event_log=event_log, amem=None)

        # Only include chat, even though current_mode is workshop
        result = await builder.build(
            query="test",
            current_mode="workshop",
            include_modes=["chat"],
        )

        assert "chat msg" in result.cross_mode_text
        assert "thought msg" not in result.cross_mode_text
        assert "workshop msg" not in result.cross_mode_text


class TestToolEvents:
    @pytest.mark.asyncio
    async def test_tool_call_and_result_formatted(self) -> None:
        events = {
            "workshop": [
                _make_event(
                    mode="workshop",
                    event_type="tool_call",
                    content="web_search",
                    metadata={"tool_name": "web_search"},
                ),
                _make_event(
                    mode="workshop",
                    event_type="tool_result",
                    content="Found 5 results",
                    metadata={"tool_name": "web_search"},
                ),
            ],
        }
        event_log = _make_event_log(events)
        builder = ContextBuilder(event_log=event_log, amem=None)

        result = await builder.build(query="test", current_mode="chat")

        assert "Used tool: web_search" in result.cross_mode_text
        assert "Tool result (web_search):" in result.cross_mode_text


class TestMemoryRecallFailure:
    @pytest.mark.asyncio
    async def test_amem_failure_returns_empty_memory(self) -> None:
        amem = MagicMock()
        amem.recall = AsyncMock(side_effect=RuntimeError("connection failed"))
        event_log = _make_event_log()
        builder = ContextBuilder(event_log=event_log, amem=amem)

        result = await builder.build(query="test", current_mode="chat")

        assert result.memory_text == ""
        assert result.memories_used == 0


class TestMemoryUsesContentFallback:
    @pytest.mark.asyncio
    async def test_uses_content_when_no_summary(self) -> None:
        zettels = [FakeZettel(id="z1", summary="", content="full content here")]
        amem = _make_amem(zettels)
        event_log = _make_event_log()
        builder = ContextBuilder(event_log=event_log, amem=amem)

        result = await builder.build(query="test", current_mode="chat")

        assert "full content here" in result.memory_text
