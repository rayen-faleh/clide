"""Tests for goal management."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import aiosqlite
import pytest

from clide.autonomy.goals import GoalManager
from clide.autonomy.models import GoalPriority, GoalStatus


@pytest.fixture
def goal_manager(tmp_path: Path) -> GoalManager:
    return GoalManager(db_path=tmp_path / "test_goals.db")


class TestGoalManager:
    async def test_create_goal(self, goal_manager: GoalManager) -> None:
        goal = await goal_manager.create("Learn Python")
        assert goal.description == "Learn Python"
        assert goal.priority == GoalPriority.MEDIUM
        assert goal.status == GoalStatus.ACTIVE
        assert goal.progress == 0.0

    async def test_get_goal(self, goal_manager: GoalManager) -> None:
        created = await goal_manager.create("Read a book")
        fetched = await goal_manager.get(created.id)
        assert fetched is not None
        assert fetched.description == "Read a book"
        assert fetched.id == created.id

    async def test_get_nonexistent(self, goal_manager: GoalManager) -> None:
        result = await goal_manager.get("nonexistent-id")
        assert result is None

    async def test_update_progress(self, goal_manager: GoalManager) -> None:
        goal = await goal_manager.create("Exercise")
        updated = await goal_manager.update(goal.id, progress=0.5)
        assert updated is not None
        assert updated.progress == 0.5

    async def test_update_status(self, goal_manager: GoalManager) -> None:
        goal = await goal_manager.create("Write code")
        updated = await goal_manager.update(goal.id, status=GoalStatus.COMPLETED)
        assert updated is not None
        assert updated.status == GoalStatus.COMPLETED

    async def test_update_notes(self, goal_manager: GoalManager) -> None:
        goal = await goal_manager.create("Study")
        updated = await goal_manager.update(goal.id, notes="Going well")
        assert updated is not None
        assert updated.notes == "Going well"

    async def test_update_nonexistent(self, goal_manager: GoalManager) -> None:
        result = await goal_manager.update("fake-id", progress=0.5)
        assert result is None

    async def test_update_clamps_progress(self, goal_manager: GoalManager) -> None:
        goal = await goal_manager.create("Test")
        updated = await goal_manager.update(goal.id, progress=1.5)
        assert updated is not None
        assert updated.progress == 1.0

    async def test_get_active_goals(self, goal_manager: GoalManager) -> None:
        await goal_manager.create("Active 1")
        await goal_manager.create("Active 2")
        g3 = await goal_manager.create("Completed")
        await goal_manager.update(g3.id, status=GoalStatus.COMPLETED)

        active = await goal_manager.get_active()
        assert len(active) == 2
        descriptions = {g.description for g in active}
        assert descriptions == {"Active 1", "Active 2"}

    async def test_get_all_goals(self, goal_manager: GoalManager) -> None:
        await goal_manager.create("Goal 1")
        await goal_manager.create("Goal 2")
        g3 = await goal_manager.create("Goal 3")
        await goal_manager.update(g3.id, status=GoalStatus.ABANDONED)

        all_goals = await goal_manager.get_all()
        assert len(all_goals) == 3

    async def test_delete_goal(self, goal_manager: GoalManager) -> None:
        goal = await goal_manager.create("To delete")
        assert await goal_manager.delete(goal.id) is True
        assert await goal_manager.get(goal.id) is None

    async def test_delete_nonexistent(self, goal_manager: GoalManager) -> None:
        assert await goal_manager.delete("fake-id") is False

    async def test_count_active(self, goal_manager: GoalManager) -> None:
        await goal_manager.create("Goal A")
        await goal_manager.create("Goal B")
        await goal_manager.create("Goal C")
        count = await goal_manager.count_active()
        assert count == 3

    async def test_count_active_excludes_completed(self, goal_manager: GoalManager) -> None:
        await goal_manager.create("Active goal")
        g2 = await goal_manager.create("Done goal")
        await goal_manager.update(g2.id, status=GoalStatus.COMPLETED)
        g3 = await goal_manager.create("Abandoned goal")
        await goal_manager.update(g3.id, status=GoalStatus.ABANDONED)
        count = await goal_manager.count_active()
        assert count == 1

    async def test_find_by_description(self, goal_manager: GoalManager) -> None:
        await goal_manager.create("Learn about astronomy")
        await goal_manager.create("Practice guitar daily")
        found = await goal_manager.find_by_description("astronomy")
        assert found is not None
        assert found.description == "Learn about astronomy"

    async def test_find_by_description_not_found(self, goal_manager: GoalManager) -> None:
        await goal_manager.create("Learn about astronomy")
        found = await goal_manager.find_by_description("nonexistent topic")
        assert found is None


class TestGoalExpiry:
    """Tests for goal auto-expiry."""

    async def test_expire_stale(self, goal_manager: GoalManager) -> None:
        """Create an old goal, verify it gets abandoned."""
        from datetime import timedelta

        goal = await goal_manager.create("Old stale goal")
        # Manually backdate the updated_at to 3 hours ago
        old_time = (datetime.utcnow() - timedelta(hours=3)).isoformat()
        async with aiosqlite.connect(goal_manager.db_path) as db:
            await db.execute(
                "UPDATE goals SET updated_at = ? WHERE id = ?",
                (old_time, goal.id),
            )
            await db.commit()

        expired = await goal_manager.expire_stale()
        assert len(expired) == 1
        assert expired[0].id == goal.id

        # Verify it's now abandoned in the DB
        updated = await goal_manager.get(goal.id)
        assert updated is not None
        assert updated.status == GoalStatus.ABANDONED
        assert "Auto-expired" in updated.notes

    async def test_expire_stale_keeps_recent(self, goal_manager: GoalManager) -> None:
        """Create a recent goal, verify it stays active."""
        goal = await goal_manager.create("Fresh goal")

        expired = await goal_manager.expire_stale()
        assert len(expired) == 0

        # Verify it's still active
        fetched = await goal_manager.get(goal.id)
        assert fetched is not None
        assert fetched.status == GoalStatus.ACTIVE

    async def test_expire_stale_ignores_completed(self, goal_manager: GoalManager) -> None:
        """Completed goals should not be expired even if old."""
        from datetime import timedelta

        goal = await goal_manager.create("Completed goal")
        await goal_manager.update(goal.id, status=GoalStatus.COMPLETED)

        # Backdate
        old_time = (datetime.utcnow() - timedelta(hours=3)).isoformat()
        async with aiosqlite.connect(goal_manager.db_path) as db:
            await db.execute(
                "UPDATE goals SET updated_at = ? WHERE id = ?",
                (old_time, goal.id),
            )
            await db.commit()

        expired = await goal_manager.expire_stale()
        assert len(expired) == 0
