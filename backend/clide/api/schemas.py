"""WebSocket message schemas shared between frontend and backend."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class WSMessageType(StrEnum):
    """WebSocket message types."""

    CHAT_MESSAGE = "chat_message"
    CHAT_RESPONSE = "chat_response"
    CHAT_RESPONSE_CHUNK = "chat_response_chunk"
    THOUGHT = "thought"
    MOOD_UPDATE = "mood_update"
    MEMORY_UPDATE = "memory_update"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    TOOL_CHECKPOINT = "tool_checkpoint"
    REWARD_GIVEN = "reward_given"
    STATE_CHANGE = "state_change"
    STATUS = "status"
    ERROR = "error"
    WORKSHOP_STARTED = "workshop_started"
    WORKSHOP_PLAN = "workshop_plan"
    WORKSHOP_DIALOGUE = "workshop_dialogue"
    WORKSHOP_STEP_UPDATE = "workshop_step_update"
    WORKSHOP_ENDED = "workshop_ended"


class AgentState(StrEnum):
    """Agent finite state machine states."""

    SLEEPING = "sleeping"
    IDLE = "idle"
    THINKING = "thinking"
    CONVERSING = "conversing"
    WORKING = "working"
    WORKSHOP = "workshop"


class WSMessage(BaseModel):
    """Base WebSocket message."""

    type: WSMessageType
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ChatMessagePayload(BaseModel):
    """Payload for chat messages."""

    content: str
    role: Literal["user", "assistant"]


class ChatResponseChunkPayload(BaseModel):
    """Payload for streaming response chunks."""

    content: str
    done: bool = False


class ThoughtPayload(BaseModel):
    """Payload for autonomous thoughts."""

    content: str
    source: Literal["autonomous", "reactive"]
    thought_type: str = "goal_oriented"


class MoodPayload(BaseModel):
    """Payload for mood updates."""

    mood: str
    intensity: float = Field(ge=0.0, le=1.0)
    reason: str = ""


class StateChangePayload(BaseModel):
    """Payload for agent state changes."""

    previous_state: AgentState
    new_state: AgentState
    reason: str = ""


class ToolCallPayload(BaseModel):
    """Payload for tool call events."""

    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    call_id: str = ""


class ToolResultPayload(BaseModel):
    """Payload for tool results."""

    call_id: str
    result: Any = None
    error: str | None = None


class ToolCheckpointPayload(BaseModel):
    """Payload for tool phase checkpoint messages."""

    content: str
    phase: int
    total_phases: int


class RewardGivePayload(BaseModel):
    """Payload for giving a reward."""

    amount: int
    reason: str


class RewardEventPayload(BaseModel):
    """Payload broadcast when reward is given."""

    amount: int
    reason: str
    total_earned: int


class ErrorPayload(BaseModel):
    """Payload for error messages."""

    message: str
    code: str = "unknown"


class WorkshopStartedPayload(BaseModel):
    """Payload for workshop session start."""

    session_id: str
    goal_description: str


class WorkshopPlanPayload(BaseModel):
    """Payload for workshop plan broadcast."""

    session_id: str
    objective: str
    approach: str
    steps: list[dict[str, Any]]


class WorkshopDialoguePayload(BaseModel):
    """Payload for workshop inner dialogue."""

    session_id: str
    content: str
    is_tool_event: bool = False


class WorkshopStepUpdatePayload(BaseModel):
    """Payload for workshop step status changes."""

    session_id: str
    step_index: int
    status: str
    result_summary: str = ""


class WorkshopEndedPayload(BaseModel):
    """Payload for workshop session end."""

    session_id: str
    status: str
    summary: str = ""
