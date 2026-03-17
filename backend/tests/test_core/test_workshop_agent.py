"""Tests for workshop-related agent methods."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clide.api.schemas import AgentState
from clide.core.agent import AgentCore
from clide.core.state import StateMachine


class TestAgentEnterWorkshop:
    """Tests for AgentCore.enter_workshop()."""

    @pytest.mark.asyncio
    async def test_enter_workshop_from_idle(self) -> None:
        agent = AgentCore()
        assert agent.state_machine.state == AgentState.IDLE

        with patch("clide.autonomy.workshop.WorkshopRunner") as mock_runner_cls:
            mock_runner = MagicMock()
            mock_runner.run = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            result = await agent.enter_workshop("g1", "Test goal")

        assert result is True
        assert agent.state_machine.state == AgentState.WORKSHOP

    @pytest.mark.asyncio
    async def test_enter_workshop_from_conversing(self) -> None:
        agent = AgentCore()
        agent.state_machine.transition(AgentState.CONVERSING, "test")

        with patch("clide.autonomy.workshop.WorkshopRunner") as mock_runner_cls:
            mock_runner = MagicMock()
            mock_runner.run = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            result = await agent.enter_workshop("g1", "Test goal")

        assert result is True
        assert agent.state_machine.state == AgentState.WORKSHOP

    @pytest.mark.asyncio
    async def test_enter_workshop_from_thinking_fails(self) -> None:
        agent = AgentCore()
        agent.state_machine.transition(AgentState.THINKING, "test")

        result = await agent.enter_workshop("g1", "Test goal")

        assert result is False
        assert agent.state_machine.state == AgentState.THINKING

    @pytest.mark.asyncio
    async def test_enter_workshop_sets_runner(self) -> None:
        agent = AgentCore()

        with patch("clide.autonomy.workshop.WorkshopRunner") as mock_runner_cls:
            mock_runner = MagicMock()
            mock_runner.run = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            await agent.enter_workshop("g1", "Test goal")

        assert agent._workshop_runner is not None

    @pytest.mark.asyncio
    async def test_enter_workshop_passes_personality(self) -> None:
        character = MagicMock()
        character.build_personality_prompt.return_value = "test personality"
        agent = AgentCore(character=character)

        with patch("clide.autonomy.workshop.WorkshopRunner") as mock_runner_cls:
            mock_runner = MagicMock()
            mock_runner.run = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            await agent.enter_workshop("g1", "Test goal")

        mock_runner_cls.assert_called_once()
        call_kwargs = mock_runner_cls.call_args[1]
        assert call_kwargs["personality_context"] == "test personality"


class TestAgentDiscardWorkshop:
    """Tests for AgentCore.discard_workshop()."""

    @pytest.mark.asyncio
    async def test_discard_when_no_workshop(self) -> None:
        agent = AgentCore()
        # Should not raise
        await agent.discard_workshop()
        assert agent.state_machine.state == AgentState.IDLE

    @pytest.mark.asyncio
    async def test_discard_cancels_runner(self) -> None:
        agent = AgentCore()

        with patch("clide.autonomy.workshop.WorkshopRunner") as mock_runner_cls:
            mock_runner = MagicMock()
            mock_runner.run = AsyncMock()
            mock_runner.cancel = MagicMock()
            mock_runner_cls.return_value = mock_runner

            await agent.enter_workshop("g1", "Test goal")
            assert agent.state_machine.state == AgentState.WORKSHOP

            await agent.discard_workshop()

        mock_runner.cancel.assert_called_once()
        assert agent._workshop_runner is None
        assert agent.state_machine.state == AgentState.IDLE

    @pytest.mark.asyncio
    async def test_discard_transitions_to_idle(self) -> None:
        agent = AgentCore()

        with patch("clide.autonomy.workshop.WorkshopRunner") as mock_runner_cls:
            mock_runner = MagicMock()
            mock_runner.run = AsyncMock()
            mock_runner.cancel = MagicMock()
            mock_runner_cls.return_value = mock_runner

            await agent.enter_workshop("g1", "Test goal")
            await agent.discard_workshop()

        assert agent.state_machine.state == AgentState.IDLE


class TestAgentGetWorkshopSession:
    """Tests for AgentCore.get_workshop_session()."""

    def test_no_session(self) -> None:
        agent = AgentCore()
        assert agent.get_workshop_session() is None

    @pytest.mark.asyncio
    async def test_with_session(self) -> None:
        agent = AgentCore()

        with patch("clide.autonomy.workshop.WorkshopRunner") as mock_runner_cls:
            mock_session = MagicMock()
            mock_runner = MagicMock()
            mock_runner.run = AsyncMock()
            mock_runner.session = mock_session
            mock_runner_cls.return_value = mock_runner

            await agent.enter_workshop("g1", "Test goal")

        assert agent.get_workshop_session() is mock_session


class TestAgentRunWorkshop:
    """Tests for AgentCore._run_workshop()."""

    @pytest.mark.asyncio
    async def test_run_workshop_cleans_up(self) -> None:
        agent = AgentCore()

        with patch("clide.autonomy.workshop.WorkshopRunner") as mock_runner_cls:
            mock_runner = MagicMock()
            mock_runner.run = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            await agent.enter_workshop("g1", "Test goal")

            # Wait for the background task
            await asyncio.sleep(0.1)
            for task in list(agent._background_tasks):
                if not task.done():
                    await task

        # After workshop completes, runner should be cleaned up
        assert agent._workshop_runner is None
        assert agent.state_machine.state == AgentState.IDLE

    @pytest.mark.asyncio
    async def test_run_workshop_handles_exception(self) -> None:
        agent = AgentCore()

        with patch("clide.autonomy.workshop.WorkshopRunner") as mock_runner_cls:
            mock_runner = MagicMock()
            mock_runner.run = AsyncMock(side_effect=Exception("boom"))
            mock_runner_cls.return_value = mock_runner

            await agent.enter_workshop("g1", "Test goal")

            # Wait for the background task
            await asyncio.sleep(0.1)
            for task in list(agent._background_tasks):
                if not task.done():
                    await task

        # Should still clean up
        assert agent._workshop_runner is None
        assert agent.state_machine.state == AgentState.IDLE


class TestWorkshopStateTransitions:
    """Tests for WORKSHOP state transitions."""

    def test_idle_to_workshop(self) -> None:
        sm = StateMachine(AgentState.IDLE)
        assert sm.can_transition(AgentState.WORKSHOP)
        sm.transition(AgentState.WORKSHOP, "start workshop")
        assert sm.state == AgentState.WORKSHOP

    def test_workshop_to_idle(self) -> None:
        sm = StateMachine(AgentState.IDLE)
        sm.transition(AgentState.WORKSHOP, "start")
        assert sm.can_transition(AgentState.IDLE)
        sm.transition(AgentState.IDLE, "workshop done")
        assert sm.state == AgentState.IDLE

    def test_workshop_to_conversing(self) -> None:
        sm = StateMachine(AgentState.IDLE)
        sm.transition(AgentState.WORKSHOP, "start")
        assert sm.can_transition(AgentState.CONVERSING)
        sm.transition(AgentState.CONVERSING, "user interrupt")
        assert sm.state == AgentState.CONVERSING

    def test_workshop_to_sleeping(self) -> None:
        sm = StateMachine(AgentState.IDLE)
        sm.transition(AgentState.WORKSHOP, "start")
        assert sm.can_transition(AgentState.SLEEPING)
        sm.transition(AgentState.SLEEPING, "schedule")
        assert sm.state == AgentState.SLEEPING

    def test_conversing_to_workshop(self) -> None:
        sm = StateMachine(AgentState.IDLE)
        sm.transition(AgentState.CONVERSING, "user msg")
        assert sm.can_transition(AgentState.WORKSHOP)
        sm.transition(AgentState.WORKSHOP, "enter workshop")
        assert sm.state == AgentState.WORKSHOP

    def test_thinking_to_workshop_invalid(self) -> None:
        sm = StateMachine(AgentState.IDLE)
        sm.transition(AgentState.THINKING, "think")
        assert not sm.can_transition(AgentState.WORKSHOP)

    def test_workshop_to_thinking_invalid(self) -> None:
        sm = StateMachine(AgentState.IDLE)
        sm.transition(AgentState.WORKSHOP, "start")
        assert not sm.can_transition(AgentState.THINKING)

    def test_workshop_to_working_invalid(self) -> None:
        sm = StateMachine(AgentState.IDLE)
        sm.transition(AgentState.WORKSHOP, "start")
        assert not sm.can_transition(AgentState.WORKING)
