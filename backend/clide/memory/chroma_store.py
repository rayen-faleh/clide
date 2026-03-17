"""ChromaDB-backed vector store for semantic memory search."""

from __future__ import annotations

from typing import Any

import chromadb
from chromadb.api.models.Collection import Collection


class ChromaMemoryStore:
    """ChromaDB store for memory embeddings and semantic search."""

    def __init__(
        self,
        collection_name: str = "clide_memories",
        persist_directory: str = "data/chromadb",
    ) -> None:
        if persist_directory:
            self._client = chromadb.PersistentClient(path=persist_directory)
        else:
            self._client = chromadb.EphemeralClient()
        self._collection: Collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    async def add(
        self,
        memory_id: str,
        content: str,
        metadata: dict[str, str] | None = None,
    ) -> None:
        """Add a memory to the vector store."""
        kwargs: dict[str, Any] = {
            "ids": [memory_id],
            "documents": [content],
        }
        if metadata:
            kwargs["metadatas"] = [metadata]
        self._collection.upsert(**kwargs)

    async def search(
        self,
        query: str,
        limit: int = 10,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Search for similar memories.

        Returns list of dicts with 'id', 'content', 'distance', 'metadata'.
        """
        total = self._collection.count()
        if total == 0:
            return []

        kwargs: dict[str, Any] = {
            "query_texts": [query],
            "n_results": min(limit, total),
        }
        if where:
            kwargs["where"] = where

        try:
            results = self._collection.query(**kwargs)
        except Exception:
            return []

        memories: list[dict[str, Any]] = []
        ids = results.get("ids")
        documents = results.get("documents")
        distances = results.get("distances")
        metadatas = results.get("metadatas")

        if ids and ids[0]:
            for i, memory_id in enumerate(ids[0]):
                memories.append(
                    {
                        "id": memory_id,
                        "content": documents[0][i] if documents and documents[0] else "",
                        "distance": distances[0][i] if distances and distances[0] else 0.0,
                        "metadata": metadatas[0][i] if metadatas and metadatas[0] else {},
                    }
                )

        return memories

    async def delete(self, memory_id: str) -> None:
        """Delete a memory from the vector store."""
        self._collection.delete(ids=[memory_id])

    async def count(self) -> int:
        """Get total number of memories in the store."""
        return int(self._collection.count())
