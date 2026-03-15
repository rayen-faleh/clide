"""Autonomy data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class ThoughtType(StrEnum):
    """Type of thought generated during autonomous thinking (DMN-inspired)."""

    MIND_WANDERING = "mind_wandering"
    SELF_REFLECTION = "self_reflection"
    SCENARIO_SIMULATION = "scenario_simulation"
    GOAL_ORIENTED = "goal_oriented"
    OBSERVATION = "observation"


class GoalStatus(StrEnum):
    """Status of a goal."""

    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class GoalPriority(StrEnum):
    """Priority level of a goal."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class Thought:
    """A thought generated during autonomous thinking."""

    id: str
    content: str
    source: str = "autonomous"  # "autonomous" or "reactive"
    thought_type: str = ThoughtType.MIND_WANDERING
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class Goal:
    """A goal the agent is working towards."""

    id: str
    description: str
    priority: GoalPriority = GoalPriority.MEDIUM
    status: GoalStatus = GoalStatus.ACTIVE
    progress: float = 0.0  # 0.0 to 1.0
    notes: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
