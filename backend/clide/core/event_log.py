"""Persistent event log using SQLite."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS agent_events (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL,
    mode        TEXT NOT NULL CHECK(mode IN ('chat','workshop','thinking')),
    event_type  TEXT NOT NULL,
    role        TEXT,
    content     TEXT,
    metadata    TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_agent_events_session_id  ON agent_events(session_id);
CREATE INDEX IF NOT EXISTS idx_agent_events_mode        ON agent_events(mode);
CREATE INDEX IF NOT EXISTS idx_agent_events_event_type  ON agent_events(event_type);
CREATE INDEX IF NOT EXISTS idx_agent_events_created_at  ON agent_events(created_at);
"""


class EventLog:
    """SQLite-backed agent event log."""

    def __init__(self, db_path: str | Path = "data/events.db") -> None:
        self._db_path = str(db_path)
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        """Create tables if not exists. Idempotent, lazy init."""
        if self._initialized:
            return
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(CREATE_TABLES_SQL)
            await db.commit()
        self._initialized = True

    async def append(
        self,
        session_id: str,
        mode: str,
        event_type: str,
        role: str | None = None,
        content: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Append an event. Returns the event id."""
        await self._ensure_initialized()
        event_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        meta_json = json.dumps(metadata or {})
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO agent_events
                    (id, session_id, mode, event_type, role, content, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (event_id, session_id, mode, event_type, role, content, meta_json, now),
            )
            await db.commit()
        return event_id

    async def get_session(self, session_id: str) -> list[dict[str, Any]]:
        """Get all events for a session, ordered by created_at ASC."""
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM agent_events WHERE session_id = ? ORDER BY created_at ASC",
                (session_id,),
            )
            rows = await cursor.fetchall()
        return [_row_to_dict(row) for row in rows]

    async def get_recent(
        self,
        limit: int = 50,
        mode: str | None = None,
        event_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get recent events, optionally filtered. Ordered by created_at DESC."""
        await self._ensure_initialized()
        conditions: list[str] = []
        params: list[Any] = []
        if mode is not None:
            conditions.append("mode = ?")
            params.append(mode)
        if event_type is not None:
            conditions.append("event_type = ?")
            params.append(event_type)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"SELECT * FROM agent_events {where} ORDER BY created_at DESC LIMIT ?",  # noqa: S608
                params,
            )
            rows = await cursor.fetchall()
        return [_row_to_dict(row) for row in rows]

    async def get_for_llm_context(
        self,
        limit: int = 50,
        modes: list[str] | None = None,
    ) -> list[dict[str, str]]:
        """Get events suitable for LLM message list.

        Filters to user_message and assistant_message types.
        Returns [{"role": ..., "content": ...}] in chronological order.
        modes defaults to ["chat"] if not specified.
        """
        await self._ensure_initialized()
        effective_modes = modes if modes is not None else ["chat"]
        placeholders = ",".join("?" * len(effective_modes))
        params: list[Any] = [*effective_modes, limit]
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"""
                SELECT role, content FROM agent_events
                WHERE mode IN ({placeholders})
                  AND event_type IN ('user_message', 'assistant_message')
                ORDER BY created_at DESC
                LIMIT ?
                """,  # noqa: S608
                params,
            )
            rows = await cursor.fetchall()
        # Reverse to get chronological (ASC) order
        result = [{"role": row["role"] or "", "content": row["content"] or ""} for row in rows]
        result.reverse()
        return result

    async def get_recent_by_type(
        self,
        event_type: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get recent events of a specific type. DESC order."""
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM agent_events WHERE event_type = ? ORDER BY created_at DESC LIMIT ?",
                (event_type, limit),
            )
            rows = await cursor.fetchall()
        return [_row_to_dict(row) for row in rows]

    async def get_since(
        self,
        since: str,
        limit: int = 200,
        mode: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get events created after *since* timestamp, ordered ASC."""
        await self._ensure_initialized()
        conditions: list[str] = ["created_at > ?"]
        params: list[Any] = [since]
        if mode is not None:
            conditions.append("mode = ?")
            params.append(mode)
        where = f"WHERE {' AND '.join(conditions)}"
        params.append(limit)
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"SELECT * FROM agent_events {where} ORDER BY created_at ASC LIMIT ?",  # noqa: S608
                params,
            )
            rows = await cursor.fetchall()
        return [_row_to_dict(row) for row in rows]

    async def count_since(self, since: str) -> int:
        """Count events created after *since* timestamp."""
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM agent_events WHERE created_at > ?",
                (since,),
            )
            row = await cursor.fetchone()
        return row[0] if row else 0

    async def prune(self, max_age_days: int = 7) -> int:
        """Delete events older than max_age_days. Returns count deleted."""
        await self._ensure_initialized()
        from datetime import timedelta

        cutoff = (datetime.now(UTC) - timedelta(days=max_age_days)).isoformat()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "DELETE FROM agent_events WHERE created_at < ?",
                (cutoff,),
            )
            deleted = cursor.rowcount
            await db.commit()
        return deleted


def _row_to_dict(row: aiosqlite.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "session_id": row["session_id"],
        "mode": row["mode"],
        "event_type": row["event_type"],
        "role": row["role"],
        "content": row["content"],
        "metadata": json.loads(row["metadata"]),
        "created_at": row["created_at"],
    }
