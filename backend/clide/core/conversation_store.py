"""Persistent conversation store using SQLite."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
)
"""


class ConversationStore:
    """SQLite-backed conversation message store."""

    def __init__(self, db_path: str | Path = "data/conversations.db") -> None:
        self.db_path = str(db_path)
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        if not self._initialized:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(CREATE_TABLE_SQL)
                await db.commit()
            self._initialized = True

    async def add_message(self, role: str, content: str) -> str:
        """Store a message. Returns the message ID."""
        await self._ensure_initialized()
        msg_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO messages (id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (msg_id, role, content, now),
            )
            await db.commit()
        logger.debug("Persisted message: role=%s, length=%d", role, len(content))
        return msg_id

    async def get_recent(self, limit: int = 50) -> list[dict[str, str]]:
        """Get the most recent messages, ordered oldest first."""
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM messages ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
            rows = await cursor.fetchall()
        # Reverse to get chronological order
        result = [
            {
                "id": row["id"],
                "role": row["role"],
                "content": row["content"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]
        result.reverse()
        return result

    async def get_for_llm(self, limit: int = 50) -> list[dict[str, str]]:
        """Get recent messages formatted for LLM context (role + content only)."""
        messages = await self.get_recent(limit=limit)
        logger.debug("Loaded %d messages from conversation history", len(messages))
        return [{"role": m["role"], "content": m["content"]} for m in messages]

    async def clear(self) -> None:
        """Clear all messages."""
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM messages")
            await db.commit()
