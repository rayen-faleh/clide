"""Tests for the SQLite memory store."""

from __future__ import annotations

from pathlib import Path

import pytest

from clide.memory.sqlite_store import SQLiteMemoryStore


@pytest.fixture
def store(tmp_path: Path) -> SQLiteMemoryStore:
    return SQLiteMemoryStore(db_path=tmp_path / "test_memory.db")


class TestSQLiteMemoryStore:
    @pytest.mark.asyncio
    async def test_save_returns_id(self, store: SQLiteMemoryStore) -> None:
        memory_id = await store.save("test content")
        assert isinstance(memory_id, str)
        assert len(memory_id) > 0

    @pytest.mark.asyncio
    async def test_save_and_get(self, store: SQLiteMemoryStore) -> None:
        memory_id = await store.save("hello world")
        memory = await store.get(memory_id)
        assert memory is not None
        assert memory.id == memory_id
        assert memory.content == "hello world"

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self, store: SQLiteMemoryStore) -> None:
        result = await store.get("nonexistent-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_search_by_keyword(self, store: SQLiteMemoryStore) -> None:
        await store.save("the cat sat on the mat")
        await store.save("the dog ran in the park")
        await store.save("cats are wonderful")

        results = await store.search("cat")
        assert len(results) == 2
        contents = [m.content for m in results]
        assert "the cat sat on the mat" in contents
        assert "cats are wonderful" in contents

    @pytest.mark.asyncio
    async def test_search_no_results(self, store: SQLiteMemoryStore) -> None:
        await store.save("hello world")
        results = await store.search("xyz_nonexistent")
        assert results == []

    @pytest.mark.asyncio
    async def test_delete_existing(self, store: SQLiteMemoryStore) -> None:
        memory_id = await store.save("to be deleted")
        result = await store.delete(memory_id)
        assert result is True
        assert await store.get(memory_id) is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, store: SQLiteMemoryStore) -> None:
        result = await store.delete("nonexistent-id")
        assert result is False

    @pytest.mark.asyncio
    async def test_list_all(self, store: SQLiteMemoryStore) -> None:
        await store.save("first")
        await store.save("second")
        await store.save("third")

        memories = await store.list_all()
        assert len(memories) == 3

    @pytest.mark.asyncio
    async def test_list_all_with_pagination(self, store: SQLiteMemoryStore) -> None:
        for i in range(5):
            await store.save(f"memory {i}")

        page1 = await store.list_all(limit=2, offset=0)
        page2 = await store.list_all(limit=2, offset=2)

        assert len(page1) == 2
        assert len(page2) == 2

        # No overlap
        ids1 = {m.id for m in page1}
        ids2 = {m.id for m in page2}
        assert ids1.isdisjoint(ids2)

    @pytest.mark.asyncio
    async def test_save_with_metadata(self, store: SQLiteMemoryStore) -> None:
        memory_id = await store.save("with meta", metadata={"source": "test", "tag": "important"})
        memory = await store.get(memory_id)
        assert memory is not None
        assert memory.metadata == {"source": "test", "tag": "important"}
