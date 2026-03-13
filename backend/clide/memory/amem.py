"""A-MEM: Agentic Memory Manager."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite

from clide.core.llm import LLMConfig
from clide.memory.chroma_store import ChromaMemoryStore
from clide.memory.models import MemoryLink, Zettel
from clide.memory.processor import MemoryProcessor

logger = logging.getLogger(__name__)

CREATE_ZETTELS_SQL = """
CREATE TABLE IF NOT EXISTS zettels (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    keywords TEXT NOT NULL DEFAULT '[]',
    tags TEXT NOT NULL DEFAULT '[]',
    context TEXT NOT NULL DEFAULT '',
    importance REAL NOT NULL DEFAULT 0.5,
    access_count INTEGER NOT NULL DEFAULT 0,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

CREATE_LINKS_SQL = """
CREATE TABLE IF NOT EXISTS memory_links (
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    relationship TEXT NOT NULL DEFAULT 'related_to',
    strength REAL NOT NULL DEFAULT 1.0,
    PRIMARY KEY (source_id, target_id),
    FOREIGN KEY (source_id) REFERENCES zettels(id),
    FOREIGN KEY (target_id) REFERENCES zettels(id)
)
"""


class AMem:
    """A-MEM: Agentic Memory with Zettelkasten-style organization."""

    def __init__(
        self,
        db_path: str | Path = "data/amem.db",
        chroma_dir: str = "data/chromadb",
        llm_config: LLMConfig | None = None,
    ) -> None:
        self.db_path = str(db_path)
        self.chroma = ChromaMemoryStore(persist_directory=chroma_dir)
        self.processor = MemoryProcessor(llm_config=llm_config)
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        if not self._initialized:
            # Ensure data directory exists
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(CREATE_ZETTELS_SQL)
                await db.execute(CREATE_LINKS_SQL)
                await db.commit()
            self._initialized = True

    async def remember(
        self,
        content: str,
        metadata: dict[str, str] | None = None,
    ) -> Zettel:
        """Process and store a new memory.

        This is the main entry point for adding memories.
        1. Fetch existing zettels for link discovery
        2. Process content through the memory processor
        3. Store in SQLite and ChromaDB
        4. Return the created Zettel
        """
        await self._ensure_initialized()

        # Get existing zettels for link finding
        existing = await self.list_recent(limit=50)

        # Process into a rich zettel
        zettel = await self.processor.process(content, existing, metadata)

        # Persist to SQLite
        await self._save_zettel(zettel)

        # Store in ChromaDB for semantic search
        await self.chroma.add(
            memory_id=zettel.id,
            content=zettel.content,
            metadata={
                "summary": zettel.summary,
                "keywords": ",".join(zettel.keywords),
                "tags": ",".join(zettel.tags),
                "importance": str(zettel.importance),
            },
        )

        return zettel

    async def recall(
        self,
        query: str,
        limit: int = 5,
        use_spreading: bool = True,
    ) -> list[Zettel]:
        """Recall memories relevant to a query.

        Uses semantic search via ChromaDB, then optionally follows links
        (activation spreading) to find related memories.
        """
        await self._ensure_initialized()

        # Semantic search via ChromaDB
        search_results = await self.chroma.search(query, limit=limit)

        # Load full zettels from SQLite
        zettels: list[Zettel] = []
        seen_ids: set[str] = set()

        for result in search_results:
            zettel = await self.get(result["id"])
            if zettel:
                zettel.access_count += 1
                await self._update_access_count(zettel.id, zettel.access_count)
                zettels.append(zettel)
                seen_ids.add(zettel.id)

        # Activation spreading: follow links to find related memories
        if use_spreading and zettels:
            spread_ids: set[str] = set()
            for z in zettels:
                for link in z.links:
                    if link.target_id not in seen_ids and link.strength > 0.5:
                        spread_ids.add(link.target_id)

            for spread_id in list(spread_ids)[:limit]:
                zettel = await self.get(spread_id)
                if zettel and zettel.id not in seen_ids:
                    zettels.append(zettel)
                    seen_ids.add(zettel.id)

        return zettels

    async def get(self, memory_id: str) -> Zettel | None:
        """Get a single zettel by ID."""
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM zettels WHERE id = ?", (memory_id,))
            row = await cursor.fetchone()
            if row is None:
                return None

            # Load links
            link_cursor = await db.execute(
                "SELECT * FROM memory_links WHERE source_id = ?", (memory_id,)
            )
            link_rows = await link_cursor.fetchall()

        zettel = self._row_to_zettel(row)
        zettel.links = [self._row_to_link(lr) for lr in link_rows]
        return zettel

    async def list_recent(self, limit: int = 50, offset: int = 0) -> list[Zettel]:
        """List recent zettels."""
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM zettels ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
            rows = await cursor.fetchall()

        return [self._row_to_zettel(row) for row in rows]

    async def delete(self, memory_id: str) -> bool:
        """Delete a zettel and its links."""
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM memory_links WHERE source_id = ? OR target_id = ?",
                (memory_id, memory_id),
            )
            cursor = await db.execute("DELETE FROM zettels WHERE id = ?", (memory_id,))
            await db.commit()
            deleted = cursor.rowcount > 0

        if deleted:
            await self.chroma.delete(memory_id)

        return deleted

    async def get_linked(self, memory_id: str) -> list[Zettel]:
        """Get all zettels linked to a given memory."""
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT z.* FROM zettels z
                   INNER JOIN memory_links ml ON z.id = ml.target_id
                   WHERE ml.source_id = ?""",
                (memory_id,),
            )
            rows = await cursor.fetchall()

        return [self._row_to_zettel(row) for row in rows]

    async def _save_zettel(self, zettel: Zettel) -> None:
        """Save a zettel to SQLite."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO zettels (id, content, summary, keywords, tags, context,
                   importance, access_count, metadata, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    zettel.id,
                    zettel.content,
                    zettel.summary,
                    json.dumps(zettel.keywords),
                    json.dumps(zettel.tags),
                    zettel.context,
                    zettel.importance,
                    zettel.access_count,
                    json.dumps(zettel.metadata),
                    zettel.created_at.isoformat(),
                    zettel.updated_at.isoformat(),
                ),
            )

            # Save links
            for link in zettel.links:
                await db.execute(
                    """INSERT OR REPLACE INTO memory_links
                       (source_id, target_id, relationship, strength)
                       VALUES (?, ?, ?, ?)""",
                    (link.source_id, link.target_id, link.relationship, link.strength),
                )

            await db.commit()

    async def _update_access_count(self, memory_id: str, count: int) -> None:
        """Update access count for a zettel."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE zettels SET access_count = ? WHERE id = ?",
                (count, memory_id),
            )
            await db.commit()

    @staticmethod
    def _row_to_zettel(row: Any) -> Zettel:
        return Zettel(
            id=row["id"],
            content=row["content"],
            summary=row["summary"],
            keywords=json.loads(row["keywords"]),
            tags=json.loads(row["tags"]),
            context=row["context"],
            importance=row["importance"],
            access_count=row["access_count"],
            metadata=json.loads(row["metadata"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _row_to_link(row: Any) -> MemoryLink:
        return MemoryLink(
            source_id=row["source_id"],
            target_id=row["target_id"],
            relationship=row["relationship"],
            strength=row["strength"],
        )
