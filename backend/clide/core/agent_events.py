"""Typed event models yielded by AgentCore.agent_step().

These replace the raw dict-based event protocol used by _tool_event_callback.
Each event represents a discrete action or observation in the agent loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

AgentMode = Literal["chat", "workshop", "thinking"]


@dataclass
class TextChunkEvent:
    """Streaming text token from the LLM."""
    content: str
    done: bool = False


@dataclass
class ToolCallEvent:
    """The LLM requested a tool call (before execution)."""
    tool_name: str
    arguments: dict[str, Any]
    call_id: str


@dataclass
class ToolResultEvent:
    """Result of a tool execution (after execution)."""
    call_id: str
    result: Any
    error: str | None = None
    success: bool = True


@dataclass
class CheckpointEvent:
    """Phase checkpoint between tool-call phases."""
    content: str
    phase: int
    total_phases: int


@dataclass
class StateChangeEvent:
    """Agent state machine transition."""
    previous_state: str
    new_state: str
    reason: str = ""


@dataclass
class LLMCallEvent:
    """Metadata about a completed LLM call (for cost tracking and logging)."""
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    purpose: str = "tool_loop"


# Union type for type-checking and isinstance dispatch
AgentStepEvent = (
    TextChunkEvent
    | ToolCallEvent
    | ToolResultEvent
    | CheckpointEvent
    | StateChangeEvent
    | LLMCallEvent
)
