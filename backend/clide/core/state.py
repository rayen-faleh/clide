"""Agent finite state machine."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import ClassVar

from clide.api.schemas import AgentState

logger = logging.getLogger(__name__)

TransitionCallback = Callable[[AgentState, AgentState, str], None]


class InvalidTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, from_state: AgentState, to_state: AgentState) -> None:
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(f"Invalid transition: {from_state} -> {to_state}")


class StateMachine:
    """Agent state machine with transition validation.

    Valid transitions:
        SLEEPING -> IDLE (wake up)
        IDLE -> THINKING (timer fires)
        IDLE -> CONVERSING (user message)
        THINKING -> IDLE (cycle complete)
        THINKING -> SLEEPING (budget exhausted / max cycles)
        THINKING -> CONVERSING (user interrupts, after finishing thought)
        CONVERSING -> IDLE (inactivity timeout)
        CONVERSING -> WORKING (tool call needed)
        WORKING -> CONVERSING (result ready, from user context)
        WORKING -> THINKING (result ready, from autonomous context)
        WORKING -> IDLE (step limit hit)
    """

    VALID_TRANSITIONS: ClassVar[dict[AgentState, set[AgentState]]] = {
        AgentState.SLEEPING: {AgentState.IDLE},
        AgentState.IDLE: {AgentState.THINKING, AgentState.CONVERSING, AgentState.WORKSHOP},
        AgentState.THINKING: {AgentState.IDLE, AgentState.SLEEPING, AgentState.CONVERSING},
        AgentState.CONVERSING: {AgentState.IDLE, AgentState.WORKING, AgentState.WORKSHOP},
        AgentState.WORKING: {AgentState.CONVERSING, AgentState.THINKING, AgentState.IDLE},
        AgentState.WORKSHOP: {AgentState.IDLE, AgentState.SLEEPING, AgentState.CONVERSING},
    }

    def __init__(self, initial_state: AgentState = AgentState.IDLE) -> None:
        self._state = initial_state
        self._lock = asyncio.Lock()
        self._transition_callbacks: list[
            tuple[AgentState | None, AgentState | None, TransitionCallback]
        ] = []

    @property
    def lock(self) -> asyncio.Lock:
        """Lock for callers that need atomic check-and-transition."""
        return self._lock

    @property
    def state(self) -> AgentState:
        """Get current state."""
        return self._state

    def can_transition(self, to_state: AgentState) -> bool:
        """Check if a transition is valid from current state."""
        return to_state in self.VALID_TRANSITIONS.get(self._state, set())

    def transition(self, to_state: AgentState, reason: str = "") -> AgentState:
        """Transition to a new state.

        Args:
            to_state: Target state
            reason: Human-readable reason for the transition

        Returns:
            The new state

        Raises:
            InvalidTransitionError: If the transition is not valid
        """
        if not self.can_transition(to_state):
            raise InvalidTransitionError(self._state, to_state)

        previous = self._state
        self._state = to_state
        logger.info("State transition: %s -> %s (reason: %s)", previous, to_state, reason)
        return self._state
