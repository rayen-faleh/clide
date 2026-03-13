"""Tests for the agent state machine."""

from __future__ import annotations

import pytest

from clide.api.schemas import AgentState
from clide.core.state import InvalidTransitionError, StateMachine


class TestStateMachineInitialization:
    def test_initial_state_is_idle(self) -> None:
        sm = StateMachine()
        assert sm.state == AgentState.IDLE

    def test_custom_initial_state(self) -> None:
        sm = StateMachine(initial_state=AgentState.SLEEPING)
        assert sm.state == AgentState.SLEEPING


class TestValidTransitions:
    def test_transition_idle_to_conversing(self) -> None:
        sm = StateMachine(initial_state=AgentState.IDLE)
        sm.transition(AgentState.CONVERSING, "user message")
        assert sm.state == AgentState.CONVERSING

    def test_transition_idle_to_thinking(self) -> None:
        sm = StateMachine(initial_state=AgentState.IDLE)
        sm.transition(AgentState.THINKING, "timer fired")
        assert sm.state == AgentState.THINKING

    def test_transition_conversing_to_idle(self) -> None:
        sm = StateMachine(initial_state=AgentState.CONVERSING)
        sm.transition(AgentState.IDLE, "inactivity timeout")
        assert sm.state == AgentState.IDLE

    def test_transition_conversing_to_working(self) -> None:
        sm = StateMachine(initial_state=AgentState.CONVERSING)
        sm.transition(AgentState.WORKING, "tool call needed")
        assert sm.state == AgentState.WORKING

    def test_transition_thinking_to_idle(self) -> None:
        sm = StateMachine(initial_state=AgentState.THINKING)
        sm.transition(AgentState.IDLE, "cycle complete")
        assert sm.state == AgentState.IDLE

    def test_transition_thinking_to_sleeping(self) -> None:
        sm = StateMachine(initial_state=AgentState.THINKING)
        sm.transition(AgentState.SLEEPING, "budget exhausted")
        assert sm.state == AgentState.SLEEPING

    def test_transition_thinking_to_conversing(self) -> None:
        sm = StateMachine(initial_state=AgentState.THINKING)
        sm.transition(AgentState.CONVERSING, "user interrupts")
        assert sm.state == AgentState.CONVERSING

    def test_transition_working_to_conversing(self) -> None:
        sm = StateMachine(initial_state=AgentState.WORKING)
        sm.transition(AgentState.CONVERSING, "result ready, user context")
        assert sm.state == AgentState.CONVERSING

    def test_transition_working_to_thinking(self) -> None:
        sm = StateMachine(initial_state=AgentState.WORKING)
        sm.transition(AgentState.THINKING, "result ready, autonomous context")
        assert sm.state == AgentState.THINKING

    def test_transition_working_to_idle(self) -> None:
        sm = StateMachine(initial_state=AgentState.WORKING)
        sm.transition(AgentState.IDLE, "step limit hit")
        assert sm.state == AgentState.IDLE

    def test_transition_sleeping_to_idle(self) -> None:
        sm = StateMachine(initial_state=AgentState.SLEEPING)
        sm.transition(AgentState.IDLE, "wake up")
        assert sm.state == AgentState.IDLE


class TestInvalidTransitions:
    def test_invalid_transition_idle_to_sleeping_raises(self) -> None:
        sm = StateMachine(initial_state=AgentState.IDLE)
        with pytest.raises(InvalidTransitionError) as exc_info:
            sm.transition(AgentState.SLEEPING)
        assert exc_info.value.from_state == AgentState.IDLE
        assert exc_info.value.to_state == AgentState.SLEEPING

    def test_invalid_transition_idle_to_working_raises(self) -> None:
        sm = StateMachine(initial_state=AgentState.IDLE)
        with pytest.raises(InvalidTransitionError):
            sm.transition(AgentState.WORKING)

    def test_invalid_transition_sleeping_to_conversing_raises(self) -> None:
        sm = StateMachine(initial_state=AgentState.SLEEPING)
        with pytest.raises(InvalidTransitionError):
            sm.transition(AgentState.CONVERSING)


class TestCanTransition:
    def test_can_transition_returns_true_for_valid(self) -> None:
        sm = StateMachine(initial_state=AgentState.IDLE)
        assert sm.can_transition(AgentState.CONVERSING) is True
        assert sm.can_transition(AgentState.THINKING) is True

    def test_can_transition_returns_false_for_invalid(self) -> None:
        sm = StateMachine(initial_state=AgentState.IDLE)
        assert sm.can_transition(AgentState.SLEEPING) is False
        assert sm.can_transition(AgentState.WORKING) is False


class TestTransitionReturnsState:
    def test_transition_returns_new_state(self) -> None:
        sm = StateMachine(initial_state=AgentState.IDLE)
        result = sm.transition(AgentState.CONVERSING, "test")
        assert result == AgentState.CONVERSING
