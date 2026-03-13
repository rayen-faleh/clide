"""Tests for goal management."""

from __future__ import annotations

from pathlib import Path

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
