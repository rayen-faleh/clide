"""Integration tests for A-MEM manager (LLM mocked)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiosqlite
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


async def _insert_zettel_with_type(
    db_path: str, content: str, memory_type: str, created_at: datetime | None = None
) -> str:
    """Insert a zettel directly into SQLite with a given metadata type."""
    zettel_id = str(uuid.uuid4())
    now = created_at or datetime.utcnow()
    metadata = json.dumps({"type": memory_type})
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO zettels (id, content, summary, keywords, tags, context,
               importance, access_count, metadata, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                zettel_id,
                content,
                "summary",
                "[]",
                "[]",
                "",
                0.5,
                0,
                metadata,
                now.isoformat(),
                now.isoformat(),
            ),
        )
        await db.commit()
    return zettel_id


class TestGetRecentByType:
    @pytest.mark.asyncio
    async def test_get_recent_by_type(self, amem: AMem) -> None:
        await amem._ensure_initialized()
        await _insert_zettel_with_type(amem.db_path, "thought 1", "thought")
        await _insert_zettel_with_type(amem.db_path, "thought 2", "thought")
        await _insert_zettel_with_type(amem.db_path, "convo 1", "conversation")

        results = await amem.get_recent_by_type("thought", limit=10)
        assert len(results) == 2
        assert all(
            json.loads(r.metadata["type"]) == "thought"
            if isinstance(r.metadata, str)
            else r.metadata.get("type") == "thought"
            for r in results
        )

    @pytest.mark.asyncio
    async def test_get_recent_by_type_ordering(self, amem: AMem) -> None:
        await amem._ensure_initialized()
        now = datetime.utcnow()
        await _insert_zettel_with_type(
            amem.db_path, "older", "thought", created_at=now - timedelta(hours=2)
        )
        await _insert_zettel_with_type(amem.db_path, "newer", "thought", created_at=now)

        results = await amem.get_recent_by_type("thought", limit=10)
        assert len(results) == 2
        assert results[0].content == "newer"
        assert results[1].content == "older"

    @pytest.mark.asyncio
    async def test_get_recent_by_type_empty(self, amem: AMem) -> None:
        await amem._ensure_initialized()
        results = await amem.get_recent_by_type("nonexistent")
        assert results == []


class TestGetRandom:
    @pytest.mark.asyncio
    async def test_get_random(self, amem: AMem) -> None:
        await amem._ensure_initialized()
        await _insert_zettel_with_type(amem.db_path, "mem 1", "thought")
        await _insert_zettel_with_type(amem.db_path, "mem 2", "thought")
        await _insert_zettel_with_type(amem.db_path, "mem 3", "conversation")

        results = await amem.get_random(limit=3)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_get_random_excludes_ids(self, amem: AMem) -> None:
        await amem._ensure_initialized()
        id1 = await _insert_zettel_with_type(amem.db_path, "mem 1", "thought")
        await _insert_zettel_with_type(amem.db_path, "mem 2", "thought")

        results = await amem.get_random(limit=10, exclude_ids=[id1])
        result_ids = [r.id for r in results]
        assert id1 not in result_ids
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_get_random_empty_store(self, amem: AMem) -> None:
        await amem._ensure_initialized()
        results = await amem.get_random(limit=3)
        assert results == []


class TestPrune:
    @pytest.fixture
    def small_amem(self, tmp_path: Path) -> AMem:
        return AMem(
            db_path=tmp_path / "amem.db",
            chroma_dir=str(tmp_path / "chromadb"),
            max_memories=3,
        )

    @pytest.mark.asyncio
    async def test_prune_removes_lowest_importance(
        self, small_amem: AMem
    ) -> None:
        await small_amem._ensure_initialized()
        # Insert 5 zettels with varying importance
        for i, imp in enumerate([0.1, 0.9, 0.3, 0.8, 0.2]):
            await _insert_zettel_with_importance(
                small_amem.db_path, f"mem {i}", imp
            )
        deleted = await small_amem.prune()
        assert deleted == 2  # 5 - 3 = 2 removed

        remaining = await small_amem.list_recent(limit=10)
        importances = sorted([z.importance for z in remaining])
        # The two lowest (0.1, 0.2) should be gone
        assert len(remaining) == 3
        assert min(importances) >= 0.3

    @pytest.mark.asyncio
    async def test_prune_noop_under_limit(self, small_amem: AMem) -> None:
        await small_amem._ensure_initialized()
        await _insert_zettel_with_type(
            small_amem.db_path, "only one", "thought"
        )
        deleted = await small_amem.prune()
        assert deleted == 0

    @pytest.mark.asyncio
    async def test_prune_empty_store(self, small_amem: AMem) -> None:
        await small_amem._ensure_initialized()
        deleted = await small_amem.prune()
        assert deleted == 0


class TestRecallFiltering:
    """Tests for exclude_types and exclude_ids parameters in AMem.recall()."""

    @pytest.mark.asyncio
    @patch("clide.memory.processor.stream_completion")
    async def test_exclude_types_filters_out_matching(
        self, mock_stream: AsyncMock, amem: AMem
    ) -> None:
        """recall(exclude_types=["thought"]) should not return thought-type memories."""
        mock_stream.side_effect = lambda msgs, cfg, **kw: _mock_extraction_stream(msgs, cfg, **kw)

        await amem.remember("Autonomous thought about X", metadata={"type": "thought"})
        z_workshop = await amem.remember("Workshop step result Y", metadata={"type": "workshop_step"})

        results = await amem.recall("X Y", limit=5, exclude_types=["thought"])
        result_ids = [z.id for z in results]

        assert z_workshop.id in result_ids
        assert all(z.metadata.get("type") != "thought" for z in results)

    @pytest.mark.asyncio
    @patch("clide.memory.processor.stream_completion")
    async def test_exclude_ids_filters_out_specific_memories(
        self, mock_stream: AsyncMock, amem: AMem
    ) -> None:
        """recall(exclude_ids={id}) should not return that memory."""
        mock_stream.side_effect = lambda msgs, cfg, **kw: _mock_extraction_stream(msgs, cfg, **kw)

        z1 = await amem.remember("Python programming tips", metadata={"type": "chat"})
        z2 = await amem.remember("Python data science notes", metadata={"type": "chat"})

        results = await amem.recall("Python", limit=5, exclude_ids={z1.id})
        result_ids = [z.id for z in results]

        assert z1.id not in result_ids
        assert z2.id in result_ids

    @pytest.mark.asyncio
    @patch("clide.memory.processor.stream_completion")
    async def test_exclude_types_and_ids_combined(
        self, mock_stream: AsyncMock, amem: AMem
    ) -> None:
        """Both filters apply simultaneously."""
        mock_stream.side_effect = lambda msgs, cfg, **kw: _mock_extraction_stream(msgs, cfg, **kw)

        z_thought = await amem.remember("Thought about coding", metadata={"type": "thought"})
        z_chat = await amem.remember("Chat about coding", metadata={"type": "chat"})
        z_workshop = await amem.remember("Workshop coding step", metadata={"type": "workshop_step"})

        results = await amem.recall(
            "coding",
            limit=5,
            exclude_types=["thought"],
            exclude_ids={z_chat.id},
        )
        result_ids = [z.id for z in results]

        assert z_thought.id not in result_ids
        assert z_chat.id not in result_ids
        assert z_workshop.id in result_ids

    @pytest.mark.asyncio
    @patch("clide.memory.processor.stream_completion")
    async def test_no_filters_returns_all_types(
        self, mock_stream: AsyncMock, amem: AMem
    ) -> None:
        """Without filters, all types are returned (regression guard)."""
        mock_stream.side_effect = lambda msgs, cfg, **kw: _mock_extraction_stream(msgs, cfg, **kw)

        z1 = await amem.remember("Thought memory", metadata={"type": "thought"})
        z2 = await amem.remember("Workshop memory", metadata={"type": "workshop"})

        results = await amem.recall("memory", limit=5)
        result_ids = [z.id for z in results]

        assert z1.id in result_ids
        assert z2.id in result_ids


async def _insert_zettel_with_importance(
    db_path: str, content: str, importance: float,
) -> str:
    """Insert a zettel with a specific importance score."""
    zettel_id = str(uuid.uuid4())
    now = datetime.utcnow()
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO zettels (id, content, summary, keywords, tags,
               context, importance, access_count, metadata,
               created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                zettel_id, content, "summary", "[]", "[]", "",
                importance, 0, "{}", now.isoformat(), now.isoformat(),
            ),
        )
        await db.commit()
    return zettel_id
