"""Tests for autonomy data models."""

from __future__ import annotations

from datetime import datetime

from clide.autonomy.models import Goal, GoalPriority, GoalStatus, Thought


class TestThought:
    def test_thought_creation(self) -> None:
        thought = Thought(id="t1", content="Hello world")
        assert thought.id == "t1"
        assert thought.content == "Hello world"
        assert thought.source == "autonomous"
        assert isinstance(thought.created_at, datetime)
        assert thought.metadata == {}

    def test_thought_reactive_source(self) -> None:
        thought = Thought(id="t2", content="Reactive", source="reactive")
        assert thought.source == "reactive"

    def test_thought_with_metadata(self) -> None:
        thought = Thought(id="t3", content="Meta", metadata={"key": "value"})
        assert thought.metadata == {"key": "value"}


class TestGoal:
    def test_goal_creation_defaults(self) -> None:
        goal = Goal(id="g1", description="Learn Python")
        assert goal.id == "g1"
        assert goal.description == "Learn Python"
        assert goal.priority == GoalPriority.MEDIUM
        assert goal.status == GoalStatus.ACTIVE
        assert goal.progress == 0.0
        assert goal.notes == ""
        assert isinstance(goal.created_at, datetime)
        assert isinstance(goal.updated_at, datetime)

    def test_goal_status_values(self) -> None:
        assert GoalStatus.ACTIVE == "active"
        assert GoalStatus.COMPLETED == "completed"
        assert GoalStatus.ABANDONED == "abandoned"

    def test_goal_priority_values(self) -> None:
        assert GoalPriority.LOW == "low"
        assert GoalPriority.MEDIUM == "medium"
        assert GoalPriority.HIGH == "high"

    def test_goal_custom_values(self) -> None:
        goal = Goal(
            id="g2",
            description="Test",
            priority=GoalPriority.HIGH,
            status=GoalStatus.COMPLETED,
            progress=0.75,
            notes="Almost done",
        )
        assert goal.priority == GoalPriority.HIGH
        assert goal.status == GoalStatus.COMPLETED
        assert goal.progress == 0.75
        assert goal.notes == "Almost done"
