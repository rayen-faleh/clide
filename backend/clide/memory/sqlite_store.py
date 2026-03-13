"""SQLite-backed memory store for MVP."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

from clide.memory.store import Memory, MemoryStore

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


class SQLiteMemoryStore(MemoryStore):
    """SQLite-backed memory store."""

    def __init__(self, db_path: str | Path = "clide_memory.db") -> None:
        self.db_path = str(db_path)
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        if not self._initialized:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(CREATE_TABLE_SQL)
                await db.commit()
            self._initialized = True

    async def save(self, content: str, metadata: dict[str, str] | None = None) -> str:
        await self._ensure_initialized()
        memory_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        meta_json = json.dumps(metadata or {})

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO memories (id, content, metadata, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (memory_id, content, meta_json, now, now),
            )
            await db.commit()

        return memory_id

    async def get(self, memory_id: str) -> Memory | None:
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM memories WHERE id = ?", (memory_id,))
            row = await cursor.fetchone()

        if row is None:
            return None

        return self._row_to_memory(row)

    async def search(self, query: str, limit: int = 10) -> list[Memory]:
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM memories WHERE content LIKE ? ORDER BY updated_at DESC LIMIT ?",
                (f"%{query}%", limit),
            )
            rows = await cursor.fetchall()

        return [self._row_to_memory(row) for row in rows]

    async def delete(self, memory_id: str) -> bool:
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            await db.commit()
            return cursor.rowcount > 0

    async def list_all(self, limit: int = 100, offset: int = 0) -> list[Memory]:
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM memories ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
            rows = await cursor.fetchall()

        return [self._row_to_memory(row) for row in rows]

    @staticmethod
    def _row_to_memory(row: aiosqlite.Row) -> Memory:
        return Memory(
            id=row["id"],
            content=row["content"],
            metadata=json.loads(row["metadata"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
