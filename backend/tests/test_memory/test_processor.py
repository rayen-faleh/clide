"""Tests for memory processor (LLM calls mocked)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest

from clide.memory.models import Zettel
from clide.memory.processor import MemoryProcessor


async def _mock_stream_valid_extraction(
    messages: list[dict[str, str]], config: object, **kwargs: object
) -> AsyncIterator[str]:
    """Mock stream_completion that returns valid extraction JSON."""
    response = (
        '{"summary": "Test summary", "keywords": ["test", "mock"],'
        ' "tags": ["factual"], "context": "Testing context", "importance": 0.8}'
    )
    for char in [response]:
        yield char


async def _mock_stream_invalid_json(
    messages: list[dict[str, str]], config: object, **kwargs: object
) -> AsyncIterator[str]:
    """Mock stream_completion that returns invalid JSON."""
    yield "this is not valid json at all"


async def _mock_stream_links(
    messages: list[dict[str, str]], config: object, **kwargs: object
) -> AsyncIterator[str]:
    """Mock stream_completion that returns link JSON."""
    content = str(messages[0]["content"])
    if "existing memories" in content.lower() or "Existing memories" in content:
        yield '[{"target_id": "existing-1", "relationship": "related_to", "strength": 0.9}]'
    else:
        response = (
            '{"summary": "New memory", "keywords": ["new"],'
            ' "tags": ["personal"], "context": "test", "importance": 0.6}'
        )
        yield response


class TestMemoryProcessor:
    @pytest.mark.asyncio
    @patch("clide.memory.processor.stream_completion")
    async def test_process_creates_zettel(self, mock_stream: AsyncMock) -> None:
        mock_stream.return_value = _mock_stream_valid_extraction([], None)
        processor = MemoryProcessor()

        zettel = await processor.process("Some interesting content")

        assert isinstance(zettel, Zettel)
        assert zettel.content == "Some interesting content"
        assert zettel.summary == "Test summary"
        assert zettel.keywords == ["test", "mock"]
        assert zettel.tags == ["factual"]
        assert zettel.importance == 0.8
        assert len(zettel.id) > 0

    @pytest.mark.asyncio
    @patch("clide.memory.processor.stream_completion")
    async def test_process_with_extraction_failure_uses_defaults(
        self, mock_stream: AsyncMock
    ) -> None:
        mock_stream.return_value = _mock_stream_invalid_json([], None)
        processor = MemoryProcessor()

        zettel = await processor.process("Some content that fails extraction")

        assert isinstance(zettel, Zettel)
        assert zettel.content == "Some content that fails extraction"
        # Should use fallback defaults
        assert zettel.summary == "Some content that fails extraction"[:100]
        assert zettel.keywords == []
        assert zettel.importance == 0.5

    @pytest.mark.asyncio
    @patch("clide.memory.processor.stream_completion")
    async def test_find_links_with_existing_memories(self, mock_stream: AsyncMock) -> None:
        mock_stream.side_effect = lambda messages, config, **kw: _mock_stream_links(
            messages, config, **kw
        )
        processor = MemoryProcessor()

        existing = [
            Zettel(id="existing-1", content="Old memory", summary="Old", keywords=["old"]),
        ]

        zettel = await processor.process("New content related to old", existing)

        assert isinstance(zettel, Zettel)
        assert len(zettel.links) == 1
        assert zettel.links[0].target_id == "existing-1"
        assert zettel.links[0].relationship == "related_to"

    @pytest.mark.asyncio
    @patch("clide.memory.processor.stream_completion")
    async def test_find_links_with_no_existing(self, mock_stream: AsyncMock) -> None:
        mock_stream.return_value = _mock_stream_valid_extraction([], None)
        processor = MemoryProcessor()

        zettel = await processor.process("Standalone content")

        assert isinstance(zettel, Zettel)
        assert zettel.links == []
