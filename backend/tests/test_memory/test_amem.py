"""Integration tests for A-MEM manager (LLM mocked)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from clide.memory.amem import AMem
from clide.memory.models import MemoryLink, Zettel


async def _mock_extraction_stream(messages: list[dict[str, str]], config: object, **kwargs: object):  # type: ignore[no-untyped-def]
    """Mock stream that returns extraction JSON."""
    content = str(messages[0].get("content", ""))
    if "existing memories" in content.lower() or "Existing memories" in content:
        yield "[]"
    else:
        yield (
            '{"summary": "Test memory", "keywords": ["test"],'
            ' "tags": ["factual"], "context": "testing", "importance": 0.7}'
        )


@pytest.fixture
def amem(tmp_path: Path) -> AMem:
    return AMem(
        db_path=tmp_path / "amem.db",
        chroma_dir=str(tmp_path / "chromadb"),
    )


class TestAMem:
    @pytest.mark.asyncio
    @patch("clide.memory.processor.stream_completion")
    async def test_remember_stores_zettel(self, mock_stream: AsyncMock, amem: AMem) -> None:
        mock_stream.side_effect = lambda msgs, cfg, **kw: _mock_extraction_stream(msgs, cfg, **kw)
        zettel = await amem.remember("Important fact to remember")

        assert isinstance(zettel, Zettel)
        assert zettel.content == "Important fact to remember"
        assert zettel.summary == "Test memory"
        assert len(zettel.id) > 0

        # Verify it was persisted
        retrieved = await amem.get(zettel.id)
        assert retrieved is not None
        assert retrieved.content == "Important fact to remember"

    @pytest.mark.asyncio
    @patch("clide.memory.processor.stream_completion")
    async def test_recall_returns_relevant(self, mock_stream: AsyncMock, amem: AMem) -> None:
        mock_stream.side_effect = lambda msgs, cfg, **kw: _mock_extraction_stream(msgs, cfg, **kw)
        await amem.remember("Python is great for data science")
        await amem.remember("JavaScript powers the web")

        results = await amem.recall("programming languages", limit=5)
        assert len(results) >= 1

    @pytest.mark.asyncio
    @patch("clide.memory.processor.stream_completion")
    async def test_recall_with_activation_spreading(
        self, mock_stream: AsyncMock, amem: AMem
    ) -> None:
        mock_stream.side_effect = lambda msgs, cfg, **kw: _mock_extraction_stream(msgs, cfg, **kw)
        # Store two memories
        z1 = await amem.remember("Machine learning basics")
        z2 = await amem.remember("Neural networks advanced")

        # Manually add a strong link between them
        link = MemoryLink(
            source_id=z1.id,
            target_id=z2.id,
            relationship="related_to",
            strength=0.9,
        )
        import aiosqlite

        async with aiosqlite.connect(str(amem.db_path)) as db:
            await db.execute(
                "INSERT OR REPLACE INTO memory_links"
                " (source_id, target_id, relationship, strength)"
                " VALUES (?, ?, ?, ?)",
                (link.source_id, link.target_id, link.relationship, link.strength),
            )
            await db.commit()

        # Recall with spreading should potentially find linked memories
        results = await amem.recall("machine learning", limit=5, use_spreading=True)
        result_ids = [r.id for r in results]
        assert z1.id in result_ids

    @pytest.mark.asyncio
    @patch("clide.memory.processor.stream_completion")
    async def test_get_by_id(self, mock_stream: AsyncMock, amem: AMem) -> None:
        mock_stream.side_effect = lambda msgs, cfg, **kw: _mock_extraction_stream(msgs, cfg, **kw)
        zettel = await amem.remember("Specific memory")
        result = await amem.get(zettel.id)
        assert result is not None
        assert result.id == zettel.id
        assert result.content == "Specific memory"

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, amem: AMem) -> None:
        result = await amem.get("nonexistent-id")
        assert result is None

    @pytest.mark.asyncio
    @patch("clide.memory.processor.stream_completion")
    async def test_delete_zettel(self, mock_stream: AsyncMock, amem: AMem) -> None:
        mock_stream.side_effect = lambda msgs, cfg, **kw: _mock_extraction_stream(msgs, cfg, **kw)
        zettel = await amem.remember("To be deleted")
        assert await amem.delete(zettel.id) is True
        assert await amem.get(zettel.id) is None
        # Deleting again should return False
        assert await amem.delete(zettel.id) is False

    @pytest.mark.asyncio
    @patch("clide.memory.processor.stream_completion")
    async def test_list_recent(self, mock_stream: AsyncMock, amem: AMem) -> None:
        mock_stream.side_effect = lambda msgs, cfg, **kw: _mock_extraction_stream(msgs, cfg, **kw)
        await amem.remember("First")
        await amem.remember("Second")
        await amem.remember("Third")

        recent = await amem.list_recent(limit=10)
        assert len(recent) == 3

    @pytest.mark.asyncio
    @patch("clide.memory.processor.stream_completion")
    async def test_get_linked(self, mock_stream: AsyncMock, amem: AMem) -> None:
        mock_stream.side_effect = lambda msgs, cfg, **kw: _mock_extraction_stream(msgs, cfg, **kw)
        z1 = await amem.remember("Source memory")
        z2 = await amem.remember("Target memory")

        # Add link manually
        import aiosqlite

        async with aiosqlite.connect(str(amem.db_path)) as db:
            await db.execute(
                "INSERT OR REPLACE INTO memory_links"
                " (source_id, target_id, relationship, strength)"
                " VALUES (?, ?, ?, ?)",
                (z1.id, z2.id, "related_to", 0.8),
            )
            await db.commit()

        linked = await amem.get_linked(z1.id)
        assert len(linked) == 1
        assert linked[0].id == z2.id
