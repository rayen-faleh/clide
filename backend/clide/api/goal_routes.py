"""Goal API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from clide.autonomy.goals import GoalManager

goal_router = APIRouter(prefix="/api/goals", tags=["goals"])

_goal_manager: GoalManager | None = None


def set_goal_manager(manager: GoalManager) -> None:
    """Set the global GoalManager instance."""
    global _goal_manager  # noqa: PLW0603
    _goal_manager = manager


def get_goal_manager() -> GoalManager:
    """Get the global GoalManager instance."""
    if _goal_manager is None:
        msg = "GoalManager not initialized"
        raise RuntimeError(msg)
    return _goal_manager


@goal_router.get("")
async def get_goals() -> dict[str, Any]:
    """Get all goals."""
    manager = get_goal_manager()
    goals = await manager.get_all()
    return {
        "goals": [
            {
                "id": g.id,
                "description": g.description,
                "priority": g.priority.value,
                "status": g.status.value,
                "progress": g.progress,
                "notes": g.notes,
                "created_at": g.created_at.isoformat(),
                "updated_at": g.updated_at.isoformat(),
            }
            for g in goals
        ],
        "count": len(goals),
    }


@goal_router.get("/active")
async def get_active_goals() -> dict[str, Any]:
    """Get active goals only."""
    manager = get_goal_manager()
    goals = await manager.get_active()
    return {
        "goals": [
            {
                "id": g.id,
                "description": g.description,
                "priority": g.priority.value,
                "status": g.status.value,
                "progress": g.progress,
                "notes": g.notes,
                "created_at": g.created_at.isoformat(),
                "updated_at": g.updated_at.isoformat(),
            }
            for g in goals
        ],
        "count": len(goals),
    }
