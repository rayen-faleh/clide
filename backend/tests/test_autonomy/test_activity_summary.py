"""Tests for the activity summarizer."""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clide.autonomy.activity_summary import ActivitySummarizer
from clide.core.llm import LLMConfig


def _make_event(content: str, event_type: str = "user_message", mode: str = "chat") -> dict:
    return {
        "id": "test-id",
        "session_id": "sess",
        "mode": mode,
        "event_type": event_type,
        "role": "user",
        "content": content,
        "metadata": {},
        "created_at": "2026-03-29T12:00:00+00:00",
    }


@pytest.fixture
def llm_config() -> LLMConfig:
    return LLMConfig(provider="ollama", model="llama3.2")


@pytest.fixture
def mock_event_log() -> MagicMock:
    log = MagicMock()
    log.count_since = AsyncMock(return_value=0)
    log.get_since = AsyncMock(return_value=[])
    return log


@pytest.fixture
def mock_amem() -> MagicMock:
    amem = MagicMock()
    amem.get_recent_by_type = AsyncMock(return_value=[])
    amem.remember = AsyncMock(return_value=None)
    return amem


class TestActivitySummarizer:
    async def test_maybe_summarize_returns_false_when_few_events(
        self,
        mock_event_log: MagicMock,
        mock_amem: MagicMock,
        llm_config: LLMConfig,
    ) -> None:
        mock_event_log.count_since.return_value = 2

        summarizer = ActivitySummarizer(
            event_log=mock_event_log,
            amem=mock_amem,
            llm_config=llm_config,
            min_events_threshold=5,
        )
        result = await summarizer.maybe_summarize()

        assert result is False
        mock_amem.remember.assert_not_called()

    async def test_maybe_summarize_generates_summary(
        self,
        mock_event_log: MagicMock,
        mock_amem: MagicMock,
        llm_config: LLMConfig,
    ) -> None:
        events = [_make_event(f"message {i}") for i in range(10)]
        mock_event_log.count_since.return_value = 10
        mock_event_log.get_since.return_value = events

        async def fake_stream(*args: object, **kwargs: object) -> AsyncIterator[str]:
            yield "Today I helped with several queries "
            yield "and explored new topics."

        with patch("clide.autonomy.activity_summary.stream_completion", side_effect=fake_stream):
            summarizer = ActivitySummarizer(
                event_log=mock_event_log,
                amem=mock_amem,
                llm_config=llm_config,
                min_events_threshold=5,
            )
            result = await summarizer.maybe_summarize()

        assert result is True
        mock_amem.remember.assert_called_once()
        call_args = mock_amem.remember.call_args
        assert call_args is not None
        content_arg = call_args[0][0]
        assert "journal" in content_arg.lower() or "Clide" in content_arg
        metadata_arg = call_args[1]["metadata"] if "metadata" in call_args[1] else call_args[0][1]
        assert metadata_arg["type"] == "activity_summary"

    async def test_maybe_summarize_updates_last_summary_at(
        self,
        mock_event_log: MagicMock,
        mock_amem: MagicMock,
        llm_config: LLMConfig,
    ) -> None:
        events = [_make_event(f"msg {i}") for i in range(6)]
        mock_event_log.count_since.return_value = 6
        mock_event_log.get_since.return_value = events

        async def fake_stream(*args: object, **kwargs: object) -> AsyncIterator[str]:
            yield "A short journal entry."

        summarizer = ActivitySummarizer(
            event_log=mock_event_log,
            amem=mock_amem,
            llm_config=llm_config,
            min_events_threshold=5,
        )
        assert summarizer._last_summary_at is None  # noqa: SLF001

        with patch("clide.autonomy.activity_summary.stream_completion", side_effect=fake_stream):
            await summarizer.maybe_summarize()

        assert summarizer._last_summary_at is not None  # noqa: SLF001

    async def test_digest_stays_under_2000_chars(
        self,
        mock_event_log: MagicMock,
        mock_amem: MagicMock,
        llm_config: LLMConfig,
    ) -> None:
        # Create 100 events each with long content
        long_content = "x" * 500
        events = [_make_event(long_content) for _ in range(100)]
        mock_event_log.count_since.return_value = 100
        mock_event_log.get_since.return_value = events

        captured_messages: list[object] = []

        async def fake_stream(
            messages: object, *args: object, **kwargs: object
        ) -> AsyncIterator[str]:
            captured_messages.append(messages)
            yield "Summary text."

        with patch("clide.autonomy.activity_summary.stream_completion", side_effect=fake_stream):
            summarizer = ActivitySummarizer(
                event_log=mock_event_log,
                amem=mock_amem,
                llm_config=llm_config,
                min_events_threshold=5,
            )
            await summarizer.maybe_summarize()

        assert len(captured_messages) == 1
        messages = captured_messages[0]
        assert isinstance(messages, list)
        # Find the user message content and check the digest portion
        user_msg = next((m for m in messages if m["role"] == "user"), None)
        assert user_msg is not None
        # The "Recent activity:" section should have digest <= 2000 chars
        content = user_msg["content"]
        activity_marker = "Recent activity:"
        if activity_marker in content:
            after_marker = content[content.index(activity_marker) + len(activity_marker):]
            # Remove the trailing "Journal entry:" part
            journal_marker = "Journal entry:"
            if journal_marker in after_marker:
                digest_section = after_marker[: after_marker.index(journal_marker)].strip()
                assert len(digest_section) <= 2000

    async def test_maybe_summarize_handles_llm_failure(
        self,
        mock_event_log: MagicMock,
        mock_amem: MagicMock,
        llm_config: LLMConfig,
    ) -> None:
        events = [_make_event(f"msg {i}") for i in range(8)]
        mock_event_log.count_since.return_value = 8
        mock_event_log.get_since.return_value = events

        async def failing_stream(*args: object, **kwargs: object) -> AsyncIterator[str]:
            raise RuntimeError("LLM is down")
            yield  # make it a generator

        with patch(
            "clide.autonomy.activity_summary.stream_completion", side_effect=failing_stream
        ):
            summarizer = ActivitySummarizer(
                event_log=mock_event_log,
                amem=mock_amem,
                llm_config=llm_config,
                min_events_threshold=5,
            )
            # Should not raise, should return False
            result = await summarizer.maybe_summarize()

        assert result is False
        mock_amem.remember.assert_not_called()

    async def test_uses_last_summary_at_as_lookback(
        self,
        mock_event_log: MagicMock,
        mock_amem: MagicMock,
        llm_config: LLMConfig,
    ) -> None:
        """When _last_summary_at is set, it should be used as the since timestamp."""
        last_summary = "2026-03-29T10:00:00+00:00"
        mock_event_log.count_since.return_value = 0  # threshold not met

        summarizer = ActivitySummarizer(
            event_log=mock_event_log,
            amem=mock_amem,
            llm_config=llm_config,
            min_events_threshold=5,
        )
        summarizer._last_summary_at = last_summary  # noqa: SLF001

        await summarizer.maybe_summarize()

        mock_event_log.count_since.assert_called_once_with(last_summary)

    async def test_uses_amem_when_no_last_summary(
        self,
        mock_event_log: MagicMock,
        mock_amem: MagicMock,
        llm_config: LLMConfig,
    ) -> None:
        """When _last_summary_at is None, query amem for the last summary."""
        amem_entry = MagicMock()
        amem_entry.created_at = None
        # Return one entry from amem
        mock_amem.get_recent_by_type.return_value = [amem_entry]
        mock_event_log.count_since.return_value = 0

        summarizer = ActivitySummarizer(
            event_log=mock_event_log,
            amem=mock_amem,
            llm_config=llm_config,
            min_events_threshold=5,
        )
        await summarizer.maybe_summarize()

        mock_amem.get_recent_by_type.assert_called_once_with("activity_summary", limit=1)
