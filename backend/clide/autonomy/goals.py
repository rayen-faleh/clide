"""Goal management for the autonomous agent."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from pathlib import Path

import aiosqlite

from clide.autonomy.models import Goal, GoalPriority, GoalStatus

logger = logging.getLogger(__name__)

CREATE_GOALS_SQL = """
CREATE TABLE IF NOT EXISTS goals (
    id TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    priority TEXT NOT NULL DEFAULT 'medium',
    status TEXT NOT NULL DEFAULT 'active',
    progress REAL NOT NULL DEFAULT 0.0,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


class GoalManager:
    """Manages agent goals with SQLite persistence."""

    def __init__(self, db_path: str | Path = "data/goals.db") -> None:
        self.db_path = str(db_path)
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        if not self._initialized:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(CREATE_GOALS_SQL)
                await db.commit()
            self._initialized = True

    async def create(
        self,
        description: str,
        priority: GoalPriority = GoalPriority.MEDIUM,
    ) -> Goal:
        """Create a new goal."""
        await self._ensure_initialized()
        now = datetime.utcnow()
        goal = Goal(
            id=str(uuid.uuid4()),
            description=description,
            priority=priority,
            created_at=now,
            updated_at=now,
        )

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO goals (id, description, priority, status, progress,
                   notes, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    goal.id,
                    goal.description,
                    goal.priority.value,
                    goal.status.value,
                    goal.progress,
                    goal.notes,
                    goal.created_at.isoformat(),
                    goal.updated_at.isoformat(),
                ),
            )
            await db.commit()

        return goal

    async def update(
        self,
        goal_id: str,
        progress: float | None = None,
        status: GoalStatus | None = None,
        notes: str | None = None,
    ) -> Goal | None:
        """Update a goal."""
        await self._ensure_initialized()
        goal = await self.get(goal_id)
        if not goal:
            return None

        if progress is not None:
            goal.progress = max(0.0, min(1.0, progress))
        if status is not None:
            goal.status = status
        if notes is not None:
            goal.notes = notes
        goal.updated_at = datetime.utcnow()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """UPDATE goals SET progress = ?, status = ?, notes = ?, updated_at = ?
                   WHERE id = ?""",
                (
                    goal.progress,
                    goal.status.value,
                    goal.notes,
                    goal.updated_at.isoformat(),
                    goal.id,
                ),
            )
            await db.commit()

        return goal

    async def get(self, goal_id: str) -> Goal | None:
        """Get a goal by ID."""
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM goals WHERE id = ?", (goal_id,))
            row = await cursor.fetchone()

        if row is None:
            return None
        return self._row_to_goal(row)

    async def get_active(self) -> list[Goal]:
        """Get all active goals."""
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM goals WHERE status = ? ORDER BY priority, created_at",
                (GoalStatus.ACTIVE.value,),
            )
            rows = await cursor.fetchall()

        return [self._row_to_goal(row) for row in rows]

    async def get_all(self) -> list[Goal]:
        """Get all goals."""
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM goals ORDER BY updated_at DESC")
            rows = await cursor.fetchall()

        return [self._row_to_goal(row) for row in rows]

    async def delete(self, goal_id: str) -> bool:
        """Delete a goal."""
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("DELETE FROM goals WHERE id = ?", (goal_id,))
            await db.commit()
            deleted: bool = cursor.rowcount > 0
            return deleted

    @staticmethod
    def _row_to_goal(row: aiosqlite.Row) -> Goal:
        return Goal(
            id=row["id"],
            description=row["description"],
            priority=GoalPriority(row["priority"]),
            status=GoalStatus(row["status"]),
            progress=row["progress"],
            notes=row["notes"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
