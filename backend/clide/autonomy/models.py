"""Autonomy data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


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
    source: str = ""  # e.g. "workshop" — used to skip spurious progress nudges
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class WorkshopStep:
    """A single step in a workshop execution plan."""

    id: str
    description: str
    tools_needed: list[str] = field(default_factory=list)
    success_criteria: str = ""
    status: str = "pending"  # pending | in_progress | completed | skipped
    result_summary: str = ""


@dataclass
class WorkshopPlan:
    """Structured plan for a workshop session."""

    objective: str
    approach: str
    steps: list[WorkshopStep] = field(default_factory=list)


@dataclass
class WorkshopSession:
    """A workshop session tracking autonomous goal pursuit."""

    id: str
    goal_id: str
    goal_description: str
    plan: WorkshopPlan | None = None
    status: str = "active"  # active | paused | completed | abandoned
    current_step_index: int = 0
    inner_dialogue: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
