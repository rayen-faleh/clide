"""Tests for ChromaDB memory store."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from clide.memory.chroma_store import ChromaMemoryStore


@pytest.fixture
def store(tmp_path: Path) -> ChromaMemoryStore:
    # Use unique collection name per test to avoid shared state
    return ChromaMemoryStore(
        collection_name=f"test_{uuid.uuid4().hex[:8]}",
        persist_directory=str(tmp_path / "chromadb"),
    )


class TestChromaMemoryStore:
    @pytest.mark.asyncio
    async def test_add_and_search(self, store: ChromaMemoryStore) -> None:
        await store.add("m1", "The cat sat on the mat")
        results = await store.search("cat sitting", limit=5)
        assert len(results) >= 1
        assert results[0]["id"] == "m1"
        assert results[0]["content"] == "The cat sat on the mat"
        assert "distance" in results[0]

    @pytest.mark.asyncio
    async def test_search_empty_store(self, store: ChromaMemoryStore) -> None:
        results = await store.search("anything")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_returns_relevant_results(self, store: ChromaMemoryStore) -> None:
        await store.add("m1", "Python is a programming language")
        await store.add("m2", "Dogs love to play fetch")
        await store.add("m3", "JavaScript runs in the browser")

        results = await store.search("coding languages", limit=2)
        result_ids = [r["id"] for r in results]
        # Programming-related docs should rank higher than dogs
        assert "m2" not in result_ids or result_ids.index("m2") > 0

    @pytest.mark.asyncio
    async def test_delete(self, store: ChromaMemoryStore) -> None:
        await store.add("m1", "To be deleted")
        assert await store.count() == 1
        await store.delete("m1")
        assert await store.count() == 0

    @pytest.mark.asyncio
    async def test_count(self, store: ChromaMemoryStore) -> None:
        assert await store.count() == 0
        await store.add("m1", "First memory")
        assert await store.count() == 1
        await store.add("m2", "Second memory")
        assert await store.count() == 2
