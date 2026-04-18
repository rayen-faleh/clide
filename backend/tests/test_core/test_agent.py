"""Tests for the agent core."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clide.api.schemas import AgentState
from clide.core.agent import AgentCore
from clide.core.conversation_store import ConversationStore
from clide.tools.models import ToolResult


async def fake_stream_completion(
    messages: list[dict[str, str]], config: object, **kwargs: object
) -> AsyncIterator[str]:
    for chunk in ["Hello", " there", "!"]:
        yield chunk


def _make_zettel_mock(
    summary: str = "test memory",
    content: str = "full content",
    metadata: dict[str, str] | None = None,
) -> MagicMock:
    """Create a mock Zettel with summary, content, and metadata."""
    z = MagicMock()
    z.summary = summary
    z.content = content
    z.metadata = metadata or {}
    z.created_at = datetime.now(UTC)
    return z


class TestAgentCore:
    def test_initial_state_is_idle(self) -> None:
        agent = AgentCore()
        assert agent.get_state() == AgentState.IDLE

    def test_init_with_optional_deps(self) -> None:
        amem = MagicMock()
        character = MagicMock()
        cost_tracker = MagicMock()
        goal_manager = MagicMock()
        agent = AgentCore(
            amem=amem,
            character=character,
            cost_tracker=cost_tracker,
            goal_manager=goal_manager,
        )
        assert agent.amem is amem
        assert agent.character is character
        assert agent.cost_tracker is cost_tracker
        assert agent.goal_manager is goal_manager

    def test_init_without_deps_defaults_to_none(self) -> None:
        agent = AgentCore()
        assert agent.amem is None
        assert agent.character is None
        assert agent.cost_tracker is None
        assert agent.goal_manager is None

    @pytest.mark.asyncio
    async def test_process_message_transitions_to_conversing_and_back(self) -> None:
        agent = AgentCore()
        states_during: list[AgentState] = []

        async def tracking_stream(
            messages: list[dict[str, str]], config: object, **kwargs: object
        ) -> AsyncIterator[str]:
            states_during.append(agent.get_state())
            for chunk in ["Hello", " there", "!"]:
                yield chunk

        with patch("clide.core.agent.stream_completion", side_effect=tracking_stream):
            async for _ in agent.process_message("hi"):
                pass
        # During streaming, state should have been CONVERSING
        assert states_during == [AgentState.CONVERSING]
        # After completion, state should be back to IDLE
        assert agent.get_state() == AgentState.IDLE

    @pytest.mark.asyncio
    async def test_process_message_adds_to_history(self) -> None:
        agent = AgentCore()
        with patch("clide.core.agent.stream_completion", side_effect=fake_stream_completion):
            async for _ in agent.process_message("hi"):
                pass
        assert len(agent.conversation_history) == 2
        assert agent.conversation_history[0]["role"] == "user"
        assert agent.conversation_history[0]["content"] == "hi"
        assert agent.conversation_history[1]["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_process_message_streams_response(self) -> None:
        agent = AgentCore()
        chunks: list[str] = []
        with patch("clide.core.agent.stream_completion", side_effect=fake_stream_completion):
            async for chunk in agent.process_message("hi"):
                chunks.append(chunk)
        assert chunks == ["Hello", " there", "!"]

    @pytest.mark.asyncio
    async def test_conversation_history_accumulates(self) -> None:
        agent = AgentCore()
        with patch("clide.core.agent.stream_completion", side_effect=fake_stream_completion):
            async for _ in agent.process_message("first"):
                pass
            async for _ in agent.process_message("second"):
                pass
        assert len(agent.conversation_history) == 4
        assert agent.conversation_history[0]["content"] == "first"
        assert agent.conversation_history[2]["content"] == "second"

    @pytest.mark.asyncio
    async def test_clear_history(self) -> None:
        agent = AgentCore()
        agent.conversation_history = [{"role": "user", "content": "test"}]
        await agent.clear_history()
        assert agent.conversation_history == []

    @pytest.mark.asyncio
    async def test_history_trimming_at_max_length(self) -> None:
        agent = AgentCore()
        agent._max_history_length = 4  # noqa: SLF001

        with patch("clide.core.agent.stream_completion", side_effect=fake_stream_completion):
            for i in range(5):
                async for _ in agent.process_message(f"msg {i}"):
                    pass

        # Should be trimmed to last 4 entries
        assert len(agent.conversation_history) == 4


class TestProcessMessageWithMemory:
    """Tests for process_message when AMem is provided."""

    @pytest.mark.asyncio
    async def test_recall_is_called_with_user_content(self) -> None:
        amem = MagicMock()
        amem.recall = AsyncMock(return_value=[])
        amem.remember = AsyncMock()

        agent = AgentCore(amem=amem)
        with patch("clide.core.agent.stream_completion", side_effect=fake_stream_completion):
            async for _ in agent.process_message("hello"):
                pass

        amem.recall.assert_awaited_once_with("hello", limit=5)

    @pytest.mark.asyncio
    async def test_remember_is_called_after_response(self) -> None:
        amem = MagicMock()
        amem.recall = AsyncMock(return_value=[])
        amem.remember = AsyncMock()

        agent = AgentCore(amem=amem)
        with patch("clide.core.agent.stream_completion", side_effect=fake_stream_completion):
            async for _ in agent.process_message("hello"):
                pass

        await asyncio.sleep(0)  # Let background task run
        amem.remember.assert_awaited_once()
        call_args = amem.remember.call_args
        assert "They asked: hello" in call_args[0][0]
        assert "I responded: Hello there!" in call_args[0][0]
        assert call_args[1]["metadata"] == {"type": "conversation"}

    @pytest.mark.asyncio
    async def test_memory_context_included_in_prompt(self) -> None:
        zettel = _make_zettel_mock(summary="User likes Python")
        amem = MagicMock()
        amem.recall = AsyncMock(return_value=[zettel])
        amem.remember = AsyncMock()

        agent = AgentCore(amem=amem)

        captured_messages: list[dict[str, str]] = []

        async def capturing_stream(
            messages: list[dict[str, str]], config: object, **kwargs: object
        ) -> AsyncIterator[str]:
            captured_messages.extend(messages)
            for chunk in ["ok"]:
                yield chunk

        with patch("clide.core.agent.stream_completion", side_effect=capturing_stream):
            async for _ in agent.process_message("hi"):
                pass

        system_msg = captured_messages[0]["content"]
        assert "User likes Python" in system_msg

    @pytest.mark.asyncio
    async def test_recall_failure_does_not_break_chat(self) -> None:
        amem = MagicMock()
        amem.recall = AsyncMock(side_effect=RuntimeError("DB down"))
        amem.remember = AsyncMock()

        agent = AgentCore(amem=amem)
        chunks: list[str] = []
        with patch("clide.core.agent.stream_completion", side_effect=fake_stream_completion):
            async for chunk in agent.process_message("hi"):
                chunks.append(chunk)

        # Chat still works despite recall failure
        assert chunks == ["Hello", " there", "!"]

    @pytest.mark.asyncio
    async def test_remember_failure_does_not_break_chat(self) -> None:
        amem = MagicMock()
        amem.recall = AsyncMock(return_value=[])
        amem.remember = AsyncMock(side_effect=RuntimeError("DB down"))

        agent = AgentCore(amem=amem)
        chunks: list[str] = []
        with patch("clide.core.agent.stream_completion", side_effect=fake_stream_completion):
            async for chunk in agent.process_message("hi"):
                chunks.append(chunk)

        assert chunks == ["Hello", " there", "!"]


class TestProcessMessageWithCharacter:
    """Tests for process_message when Character is provided."""

    @pytest.mark.asyncio
    async def test_personality_prompt_is_used(self) -> None:
        character = MagicMock()
        character.build_personality_prompt.return_value = "You are extra witty."
        character.mood = MagicMock()
        character.save = AsyncMock()

        agent = AgentCore(character=character)

        captured_messages: list[dict[str, str]] = []

        async def capturing_stream(
            messages: list[dict[str, str]], config: object, **kwargs: object
        ) -> AsyncIterator[str]:
            captured_messages.extend(messages)
            for chunk in ["ok"]:
                yield chunk

        with patch("clide.core.agent.stream_completion", side_effect=capturing_stream):
            async for _ in agent.process_message("hi"):
                pass

        system_msg = captured_messages[0]["content"]
        assert "You are extra witty." in system_msg

    @pytest.mark.asyncio
    async def test_mood_transition_called(self) -> None:
        character = MagicMock()
        character.build_personality_prompt.return_value = ""
        character.mood = MagicMock()
        character.save = AsyncMock()

        agent = AgentCore(character=character)
        with patch("clide.core.agent.stream_completion", side_effect=fake_stream_completion):
            async for _ in agent.process_message("hi"):
                pass

        await asyncio.sleep(0)  # Let background task run
        character.mood.transition.assert_called_once_with("content", 0.6, "conversation")
        character.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_character_failure_does_not_break_chat(self) -> None:
        character = MagicMock()
        character.build_personality_prompt.return_value = ""
        character.mood = MagicMock()
        character.mood.transition.side_effect = RuntimeError("mood broke")
        character.save = AsyncMock()

        agent = AgentCore(character=character)
        chunks: list[str] = []
        with patch("clide.core.agent.stream_completion", side_effect=fake_stream_completion):
            async for chunk in agent.process_message("hi"):
                chunks.append(chunk)

        assert chunks == ["Hello", " there", "!"]


class TestProcessMessageWithoutDeps:
    """Backward compatibility — AgentCore without optional deps."""

    @pytest.mark.asyncio
    async def test_works_without_any_deps(self) -> None:
        agent = AgentCore()
        chunks: list[str] = []
        with patch("clide.core.agent.stream_completion", side_effect=fake_stream_completion):
            async for chunk in agent.process_message("hi"):
                chunks.append(chunk)

        assert chunks == ["Hello", " there", "!"]
        assert len(agent.conversation_history) == 2
        assert agent.get_state() == AgentState.IDLE


class TestAutonomousThink:
    """Tests for autonomous_think method."""

    @pytest.mark.asyncio
    async def test_returns_thought_tuple(self) -> None:
        agent = AgentCore()
        mock_thought = MagicMock()
        mock_thought.content = "I wonder about the stars"
        mock_thought.metadata = {"topic": "stars", "follow_up": ""}
        mock_thought.thought_type = "mind_wandering"

        with patch("clide.autonomy.thinker.Thinker") as mock_thinker_cls:
            thinker_instance = MagicMock()
            thinker_instance.think = AsyncMock(return_value=(mock_thought, "curious", 0.7))
            mock_thinker_cls.return_value = thinker_instance

            result = await agent.autonomous_think()

        assert result is not None
        assert len(result) == 4
        assert result[0] == "I wonder about the stars"
        assert result[1] == "curious"
        assert result[2] == 0.7

    @pytest.mark.asyncio
    async def test_transitions_to_thinking_and_back(self) -> None:
        agent = AgentCore()
        assert agent.get_state() == AgentState.IDLE

        states_during: list[AgentState] = []

        mock_thought = MagicMock()
        mock_thought.content = "hmm"
        mock_thought.metadata = {"topic": "", "follow_up": ""}

        async def capturing_think(**kwargs: object) -> tuple[MagicMock, str, float]:
            states_during.append(agent.get_state())
            return mock_thought, "contemplative", 0.5

        with patch("clide.autonomy.thinker.Thinker") as mock_thinker_cls:
            thinker_instance = MagicMock()
            thinker_instance.think = capturing_think
            mock_thinker_cls.return_value = thinker_instance

            await agent.autonomous_think()

        # During thinking, state should have been THINKING
        assert states_during == [AgentState.THINKING]
        # After thinking, should be back to IDLE
        assert agent.get_state() == AgentState.IDLE

    @pytest.mark.asyncio
    async def test_returns_none_when_cannot_transition(self) -> None:
        agent = AgentCore()
        # Transition to CONVERSING — can't go to THINKING from there
        agent.state_machine.transition(AgentState.CONVERSING, "test")

        result = await agent.autonomous_think()
        assert result is None
        # State should remain unchanged
        assert agent.get_state() == AgentState.CONVERSING

    @pytest.mark.asyncio
    async def test_transitions_back_to_idle_on_failure(self) -> None:
        agent = AgentCore()

        with patch("clide.autonomy.thinker.Thinker") as mock_thinker_cls:
            thinker_instance = MagicMock()
            thinker_instance.think = AsyncMock(side_effect=RuntimeError("LLM down"))
            mock_thinker_cls.return_value = thinker_instance

            result = await agent.autonomous_think()

        assert result is None
        assert agent.get_state() == AgentState.IDLE

    @pytest.mark.asyncio
    async def test_stores_thought_to_memory_with_rich_metadata(self) -> None:
        amem = MagicMock()
        amem.recall = AsyncMock(return_value=[])
        amem.remember = AsyncMock()

        agent = AgentCore(amem=amem)

        mock_thought = MagicMock()
        mock_thought.content = "Deep reflection"
        mock_thought.metadata = {"topic": "philosophy", "follow_up": "explore more"}

        with patch("clide.autonomy.thinker.Thinker") as mock_thinker_cls:
            thinker_instance = MagicMock()
            thinker_instance.think = AsyncMock(return_value=(mock_thought, "contemplative", 0.5))
            mock_thinker_cls.return_value = thinker_instance

            await agent.autonomous_think()

        await asyncio.sleep(0)  # Let background task run
        amem.remember.assert_awaited_once()
        call_args = amem.remember.call_args
        assert "Deep reflection" in call_args[0][0]
        assert call_args[1]["metadata"]["type"] == "thought"
        assert call_args[1]["metadata"]["source"] == "autonomous"
        assert call_args[1]["metadata"]["topic"] == "philosophy"
        assert call_args[1]["metadata"]["follow_up"] == "explore more"

    @pytest.mark.asyncio
    async def test_updates_character_mood(self) -> None:
        character = MagicMock()
        character.mood = MagicMock()
        character.mood.describe.return_value = "feeling neutral"
        character.build_personality_prompt.return_value = ""
        character.opinions = MagicMock()
        character.opinions.all.return_value = []
        character.save = AsyncMock()

        agent = AgentCore(character=character)

        mock_thought = MagicMock()
        mock_thought.content = "Interesting"
        mock_thought.metadata = {"topic": "", "follow_up": ""}

        with patch("clide.autonomy.thinker.Thinker") as mock_thinker_cls:
            thinker_instance = MagicMock()
            thinker_instance.think = AsyncMock(return_value=(mock_thought, "curious", 0.8))
            mock_thinker_cls.return_value = thinker_instance

            await agent.autonomous_think()

        await asyncio.sleep(0)  # Let background task run
        character.mood.transition.assert_called_once_with("curious", 0.8, "autonomous thinking")
        character.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_uses_semantic_recall_instead_of_list_recent(self) -> None:
        """Verify that autonomous_think uses amem.recall (semantic) not list_recent."""
        amem = MagicMock()
        amem.recall = AsyncMock(return_value=[])
        amem.remember = AsyncMock()

        agent = AgentCore(amem=amem)

        mock_thought = MagicMock()
        mock_thought.content = "thought"
        mock_thought.metadata = {"topic": "", "follow_up": ""}

        with patch("clide.autonomy.thinker.Thinker") as mock_thinker_cls:
            thinker_instance = MagicMock()
            thinker_instance.think = AsyncMock(return_value=(mock_thought, "neutral", 0.5))
            mock_thinker_cls.return_value = thinker_instance

            await agent.autonomous_think()

        # recall should be called (for thought history + memory context)
        assert amem.recall.await_count >= 1
        # list_recent should NOT be called
        amem.list_recent.assert_not_called()

    @pytest.mark.asyncio
    async def test_gathers_personality_context(self) -> None:
        character = MagicMock()
        character.mood = MagicMock()
        character.mood.describe.return_value = "feeling curious"
        character.build_personality_prompt.return_value = "You are deeply curious."
        character.opinions = MagicMock()
        character.opinions.all.return_value = []
        character.save = AsyncMock()

        agent = AgentCore(character=character)

        mock_thought = MagicMock()
        mock_thought.content = "thought"
        mock_thought.metadata = {"topic": "", "follow_up": ""}

        captured_kwargs: dict[str, object] = {}

        async def capturing_think(**kwargs: object) -> tuple[MagicMock, str, float]:
            captured_kwargs.update(kwargs)
            return mock_thought, "neutral", 0.5

        with patch("clide.autonomy.thinker.Thinker") as mock_thinker_cls:
            thinker_instance = MagicMock()
            thinker_instance.think = capturing_think
            mock_thinker_cls.return_value = thinker_instance

            await agent.autonomous_think()

        assert "You are deeply curious." in str(captured_kwargs.get("personality_context", ""))

    @pytest.mark.asyncio
    async def test_gathers_opinions_context(self) -> None:
        from clide.character.opinions import Opinion

        character = MagicMock()
        character.mood = MagicMock()
        character.mood.describe.return_value = "feeling neutral"
        character.build_personality_prompt.return_value = ""
        character.opinions = MagicMock()
        character.opinions.all.return_value = [
            Opinion(topic="AI safety", stance="very important", confidence=0.9),
        ]
        character.save = AsyncMock()

        agent = AgentCore(character=character)

        mock_thought = MagicMock()
        mock_thought.content = "thought"
        mock_thought.metadata = {"topic": "", "follow_up": ""}
        mock_thought.thought_type = "goal_oriented"

        captured_kwargs: dict[str, object] = {}

        async def capturing_think(**kwargs: object) -> tuple[MagicMock, str, float]:
            captured_kwargs.update(kwargs)
            return mock_thought, "neutral", 0.5

        with (
            patch("clide.autonomy.thinker.Thinker") as mock_thinker_cls,
            patch("clide.core.agent.random") as mock_random,
        ):
            mock_random.choices.return_value = ["goal_oriented"]
            thinker_instance = MagicMock()
            thinker_instance.think = capturing_think
            mock_thinker_cls.return_value = thinker_instance

            await agent.autonomous_think()

        opinions_ctx = str(captured_kwargs.get("opinions_context", ""))
        assert "AI safety" in opinions_ctx
        assert "very important" in opinions_ctx

    @pytest.mark.asyncio
    async def test_gathers_goals_context(self) -> None:
        goal_manager = MagicMock()
        mock_goal = MagicMock()
        mock_goal.description = "Learn about astronomy"
        mock_goal.progress = 0.3
        mock_goal.created_at = datetime.now(UTC)
        goal_manager.get_active = AsyncMock(return_value=[mock_goal])

        agent = AgentCore(goal_manager=goal_manager)

        mock_thought = MagicMock()
        mock_thought.content = "thought"
        mock_thought.metadata = {"topic": "", "follow_up": ""}
        mock_thought.thought_type = "goal_oriented"

        captured_kwargs: dict[str, object] = {}

        async def capturing_think(**kwargs: object) -> tuple[MagicMock, str, float]:
            captured_kwargs.update(kwargs)
            return mock_thought, "neutral", 0.5

        with (
            patch("clide.autonomy.thinker.Thinker") as mock_thinker_cls,
            patch("clide.core.agent.random") as mock_random,
        ):
            mock_random.choices.return_value = ["goal_oriented"]
            thinker_instance = MagicMock()
            thinker_instance.think = capturing_think
            mock_thinker_cls.return_value = thinker_instance

            await agent.autonomous_think()

        goals_ctx = str(captured_kwargs.get("goals_context", ""))
        assert "Learn about astronomy" in goals_ctx

    @pytest.mark.asyncio
    async def test_gathers_thought_history(self) -> None:
        past_thought = _make_zettel_mock(
            content="Autonomous thought: I was pondering the nature of consciousness",
            metadata={"type": "thought"},
        )
        random_mem = _make_zettel_mock(
            summary="Random old memory",
            content="Some old conversation",
        )
        random_mem.id = "rand-1"
        past_thought.id = "thought-1"
        amem = MagicMock()
        amem.get_recent_by_type = AsyncMock(return_value=[past_thought])
        amem.get_random = AsyncMock(return_value=[random_mem])
        amem.recall = AsyncMock(return_value=[])
        amem.remember = AsyncMock()

        agent = AgentCore(amem=amem)

        mock_thought = MagicMock()
        mock_thought.content = "new thought"
        mock_thought.metadata = {"topic": "", "follow_up": ""}
        mock_thought.thought_type = "goal_oriented"

        captured_kwargs: dict[str, object] = {}

        async def capturing_think(**kwargs: object) -> tuple[MagicMock, str, float]:
            captured_kwargs.update(kwargs)
            return mock_thought, "neutral", 0.5

        with (
            patch("clide.autonomy.thinker.Thinker") as mock_thinker_cls,
            patch("clide.core.agent.random") as mock_random,
        ):
            mock_random.choices.return_value = ["goal_oriented"]
            thinker_instance = MagicMock()
            thinker_instance.think = capturing_think
            mock_thinker_cls.return_value = thinker_instance

            await agent.autonomous_think()

        thought_hist = str(captured_kwargs.get("thought_history", ""))
        assert "pondering the nature of consciousness" in thought_hist
        assert "[Recent thought]" in thought_hist
        assert "[Past memory]" in thought_hist

    @pytest.mark.asyncio
    async def test_uses_follow_up_from_previous_thought_as_query(self) -> None:
        """If a previous thought has a follow_up, use it as the recall query."""
        past_thought = _make_zettel_mock(
            content="Autonomous thought: pondering",
            metadata={"type": "thought", "follow_up": "explore fractals", "topic": "math"},
        )
        past_thought.id = "thought-1"
        amem = MagicMock()

        # Return thought for "thought" type, empty for "conversation" type
        async def mock_get_recent_by_type(memory_type: str, limit: int = 5) -> list:  # type: ignore[type-arg]
            if memory_type == "thought":
                return [past_thought]
            return []  # No recent conversations

        amem.get_recent_by_type = mock_get_recent_by_type
        amem.get_random = AsyncMock(return_value=[])
        amem.recall = AsyncMock(return_value=[])
        amem.remember = AsyncMock()

        agent = AgentCore(amem=amem)

        mock_thought = MagicMock()
        mock_thought.content = "thought"
        mock_thought.metadata = {"topic": "", "follow_up": ""}

        with patch("clide.autonomy.thinker.Thinker") as mock_thinker_cls:
            thinker_instance = MagicMock()
            thinker_instance.think = AsyncMock(return_value=(mock_thought, "neutral", 0.5))
            mock_thinker_cls.return_value = thinker_instance

            await agent.autonomous_think()

        # The recall call for memory_context should use "explore fractals" as query
        recall_calls = amem.recall.call_args_list
        queries = [call[0][0] for call in recall_calls]
        assert "explore fractals" in queries

    @pytest.mark.asyncio
    async def test_still_works_without_any_deps(self) -> None:
        """Backward compat: autonomous_think works with no amem/character/goals."""
        agent = AgentCore()

        mock_thought = MagicMock()
        mock_thought.content = "standalone thought"
        mock_thought.metadata = {"topic": "", "follow_up": ""}
        mock_thought.thought_type = "mind_wandering"

        with patch("clide.autonomy.thinker.Thinker") as mock_thinker_cls:
            thinker_instance = MagicMock()
            thinker_instance.think = AsyncMock(return_value=(mock_thought, "neutral", 0.5))
            mock_thinker_cls.return_value = thinker_instance

            result = await agent.autonomous_think()

        assert result is not None
        assert len(result) == 4
        assert result[0] == "standalone thought"
        assert result[1] == "neutral"
        assert result[2] == 0.5

    @pytest.mark.asyncio
    async def test_gathers_memory_context_for_thinking(self) -> None:
        zettel = _make_zettel_mock(summary="Recent chat about AI")
        amem = MagicMock()
        amem.recall = AsyncMock(return_value=[zettel])
        amem.remember = AsyncMock()

        agent = AgentCore(amem=amem)

        mock_thought = MagicMock()
        mock_thought.content = "thought"
        mock_thought.metadata = {"topic": "", "follow_up": ""}

        captured_kwargs: dict[str, object] = {}

        async def capturing_think(**kwargs: object) -> tuple[MagicMock, str, float]:
            captured_kwargs.update(kwargs)
            return mock_thought, "neutral", 0.5

        with patch("clide.autonomy.thinker.Thinker") as mock_thinker_cls:
            thinker_instance = MagicMock()
            thinker_instance.think = capturing_think
            mock_thinker_cls.return_value = thinker_instance

            await agent.autonomous_think()

        assert "Recent chat about AI" in str(captured_kwargs.get("memory_context", ""))


class TestVariableThoughtTypes:
    """Tests for variable thought type selection in autonomous_think."""

    @pytest.mark.asyncio
    async def test_thought_type_selection_weighted(self) -> None:
        """Verify random.choices is called with the correct weights."""
        from clide.core.agent import THOUGHT_TYPE_WEIGHTS

        agent = AgentCore()

        mock_thought = MagicMock()
        mock_thought.content = "test thought"
        mock_thought.metadata = {"topic": "", "follow_up": ""}
        mock_thought.thought_type = "mind_wandering"

        with (
            patch("clide.autonomy.thinker.Thinker") as mock_thinker_cls,
            patch("clide.core.agent.random") as mock_random,
        ):
            mock_random.choices.return_value = ["mind_wandering"]
            thinker_instance = MagicMock()
            thinker_instance.think = AsyncMock(return_value=(mock_thought, "neutral", 0.5))
            mock_thinker_cls.return_value = thinker_instance

            await agent.autonomous_think()

        mock_random.choices.assert_called_once()
        call_args = mock_random.choices.call_args
        types = call_args[0][0]
        weights = call_args[1]["weights"]
        assert len(types) == len(THOUGHT_TYPE_WEIGHTS)
        assert len(weights) == len(THOUGHT_TYPE_WEIGHTS)
        # Verify mind_wandering has the highest weight
        mw_idx = types.index("mind_wandering")
        assert weights[mw_idx] == 40

    @pytest.mark.asyncio
    async def test_goal_oriented_gathers_full_context(self) -> None:
        """Goal-oriented type should gather goals, opinions, tools context."""
        character = MagicMock()
        character.mood = MagicMock()
        character.mood.describe.return_value = "neutral"
        character.build_personality_prompt.return_value = "personality"
        character.opinions = MagicMock()
        opinion = MagicMock()
        opinion.topic = "AI"
        opinion.stance = "positive"
        opinion.confidence = 0.8
        opinion.formed_at = datetime.now(UTC)
        character.opinions.all.return_value = [opinion]
        character.save = AsyncMock()

        goal_manager = MagicMock()
        goal_manager.get_active = AsyncMock(return_value=[])
        goal_manager.expire_stale = AsyncMock()

        agent = AgentCore(character=character, goal_manager=goal_manager)

        mock_thought = MagicMock()
        mock_thought.content = "goal thought"
        mock_thought.metadata = {"topic": "goals", "follow_up": ""}
        mock_thought.thought_type = "goal_oriented"

        captured_kwargs: dict[str, object] = {}

        async def capturing_think(**kwargs: object) -> tuple[MagicMock, str, float]:
            captured_kwargs.update(kwargs)
            return mock_thought, "focused", 0.8

        with (
            patch("clide.autonomy.thinker.Thinker") as mock_thinker_cls,
            patch("clide.core.agent.random") as mock_random,
        ):
            mock_random.choices.return_value = ["goal_oriented"]
            thinker_instance = MagicMock()
            thinker_instance.think = capturing_think
            mock_thinker_cls.return_value = thinker_instance

            await agent.autonomous_think()

        # Goal-oriented should include goals and opinions context
        assert "goals_context" in captured_kwargs
        assert "opinions_context" in captured_kwargs

    @pytest.mark.asyncio
    async def test_non_goal_skips_heavy_context(self) -> None:
        """Non-goal types should skip goals, opinions, tools, thought history."""
        character = MagicMock()
        character.mood = MagicMock()
        character.mood.describe.return_value = "neutral"
        character.build_personality_prompt.return_value = "personality"
        character.opinions = MagicMock()
        character.opinions.all.return_value = []
        character.save = AsyncMock()

        goal_manager = MagicMock()
        goal_manager.get_active = AsyncMock(return_value=[])
        goal_manager.expire_stale = AsyncMock()

        agent = AgentCore(character=character, goal_manager=goal_manager)

        mock_thought = MagicMock()
        mock_thought.content = "wandering thought"
        mock_thought.metadata = {}
        mock_thought.thought_type = "mind_wandering"

        captured_kwargs: dict[str, object] = {}

        async def capturing_think(**kwargs: object) -> tuple[MagicMock, str, float]:
            captured_kwargs.update(kwargs)
            return mock_thought, "playful", 0.4

        with (
            patch("clide.autonomy.thinker.Thinker") as mock_thinker_cls,
            patch("clide.core.agent.random") as mock_random,
        ):
            mock_random.choices.return_value = ["mind_wandering"]
            thinker_instance = MagicMock()
            thinker_instance.think = capturing_think
            mock_thinker_cls.return_value = thinker_instance

            await agent.autonomous_think()

        # Non-goal types should have empty heavy context (goals/opinions/tools)
        assert captured_kwargs.get("goals_context", "") == ""
        assert captured_kwargs.get("opinions_context", "") == ""
        assert captured_kwargs.get("tools_context", "") == ""
        # thought_history is now gathered for ALL types (no amem here, so still empty)
        assert captured_kwargs.get("thought_history", "") == ""

    @pytest.mark.asyncio
    async def test_autonomous_think_returns_thought_type(self) -> None:
        """Verify autonomous_think returns 4-element tuple with thought_type."""
        agent = AgentCore()

        mock_thought = MagicMock()
        mock_thought.content = "observation thought"
        mock_thought.metadata = {}
        mock_thought.thought_type = "observation"

        with (
            patch("clide.autonomy.thinker.Thinker") as mock_thinker_cls,
            patch("clide.core.agent.random") as mock_random,
        ):
            mock_random.choices.return_value = ["observation"]
            thinker_instance = MagicMock()
            thinker_instance.think = AsyncMock(return_value=(mock_thought, "neutral", 0.3))
            mock_thinker_cls.return_value = thinker_instance

            result = await agent.autonomous_think()

        assert result is not None
        assert len(result) == 4
        thought_content, mood, intensity, thought_type = result
        assert thought_content == "observation thought"
        assert thought_type == "observation"


class TestThinkingThoughtHistoryUniversal:
    """Tests that thought_history is gathered for ALL thought types, not just goal-oriented."""

    @pytest.mark.asyncio
    async def test_non_goal_receives_thought_history_when_amem_present(self) -> None:
        """mind_wandering should receive thought_history when amem has prior thoughts."""
        from datetime import UTC, datetime

        from clide.memory.models import Zettel

        amem = MagicMock()
        amem.remember = AsyncMock()
        amem.get_recent_by_type = AsyncMock(return_value=[])
        amem.get_random = AsyncMock(return_value=[])

        # Provide a prior thought via get_recent_by_type
        prior_zettel = MagicMock(spec=Zettel)
        prior_zettel.id = "z-prior"
        prior_zettel.content = "I was thinking about fractals"
        prior_zettel.summary = "fractals thought"
        prior_zettel.created_at = datetime.now(UTC)
        amem.get_recent_by_type = AsyncMock(return_value=[prior_zettel])
        amem.get_random = AsyncMock(return_value=[])

        agent = AgentCore(amem=amem)

        mock_thought = MagicMock()
        mock_thought.content = "wandering"
        mock_thought.metadata = {}
        mock_thought.thought_type = "mind_wandering"

        captured_kwargs: dict[str, object] = {}

        async def capturing_think(**kwargs: object) -> tuple[MagicMock, str, float]:
            captured_kwargs.update(kwargs)
            return mock_thought, "playful", 0.4

        with (
            patch("clide.autonomy.thinker.Thinker") as mock_thinker_cls,
            patch("clide.core.agent.random") as mock_random,
        ):
            mock_random.choices.return_value = ["mind_wandering"]
            thinker_instance = MagicMock()
            thinker_instance.think = capturing_think
            mock_thinker_cls.return_value = thinker_instance

            await agent.autonomous_think()

        assert "fractals" in str(captured_kwargs.get("thought_history", ""))

    @pytest.mark.asyncio
    async def test_non_goal_thought_history_empty_without_amem(self) -> None:
        """Without amem, thought_history stays empty for non-goal types (no crash)."""
        agent = AgentCore()  # no amem

        mock_thought = MagicMock()
        mock_thought.content = "observation"
        mock_thought.metadata = {}
        mock_thought.thought_type = "observation"

        captured_kwargs: dict[str, object] = {}

        async def capturing_think(**kwargs: object) -> tuple[MagicMock, str, float]:
            captured_kwargs.update(kwargs)
            return mock_thought, "neutral", 0.3

        with (
            patch("clide.autonomy.thinker.Thinker") as mock_thinker_cls,
            patch("clide.core.agent.random") as mock_random,
        ):
            mock_random.choices.return_value = ["observation"]
            thinker_instance = MagicMock()
            thinker_instance.think = capturing_think
            mock_thinker_cls.return_value = thinker_instance

            await agent.autonomous_think()

        assert captured_kwargs.get("thought_history", "") == ""


class TestThinkingContextDeduplication:
    """Tests that semantic recall excludes types already injected explicitly."""

    @pytest.mark.asyncio
    async def test_context_builder_excludes_thought_type(self) -> None:
        """context_builder.build() is called with exclude_types containing 'thought'."""
        from clide.core.context_builder import ContextResult

        mock_builder = MagicMock()
        mock_builder.build = AsyncMock(
            return_value=ContextResult(memory_text="", cross_mode_text="", memories_used=0)
        )

        amem = MagicMock()
        amem.remember = AsyncMock()
        amem.get_recent_by_type = AsyncMock(return_value=[])
        amem.get_random = AsyncMock(return_value=[])

        agent = AgentCore(amem=amem)
        agent.context_builder = mock_builder

        mock_thought = MagicMock()
        mock_thought.content = "test"
        mock_thought.metadata = {}
        mock_thought.thought_type = "mind_wandering"

        with (
            patch("clide.autonomy.thinker.Thinker") as mock_thinker_cls,
            patch("clide.core.agent.random") as mock_random,
        ):
            mock_random.choices.return_value = ["mind_wandering"]
            thinker_instance = MagicMock()
            thinker_instance.think = AsyncMock(return_value=(mock_thought, "neutral", 0.4))
            mock_thinker_cls.return_value = thinker_instance

            await agent.autonomous_think()

        mock_builder.build.assert_awaited_once()
        call_kwargs = mock_builder.build.call_args[1]
        assert "thought" in call_kwargs.get("exclude_types", [])

    @pytest.mark.asyncio
    async def test_context_builder_also_excludes_conversation_when_fresh_convos(self) -> None:
        """When recent_conversation_context is populated, 'conversation' is also excluded."""
        from datetime import UTC, datetime

        from clide.core.context_builder import ContextResult
        from clide.memory.models import Zettel

        mock_builder = MagicMock()
        mock_builder.build = AsyncMock(
            return_value=ContextResult(memory_text="", cross_mode_text="", memories_used=0)
        )

        # Fresh conversation (< 10 minutes ago)
        fresh_convo = MagicMock(spec=Zettel)
        fresh_convo.id = "c1"
        fresh_convo.content = "User asked about Python"
        fresh_convo.summary = "Python discussion"
        fresh_convo.created_at = datetime.now(UTC)

        amem = MagicMock()
        amem.remember = AsyncMock()
        amem.get_recent_by_type = AsyncMock(side_effect=lambda t, limit=3: (
            [fresh_convo] if t == "conversation" else []
        ))
        amem.get_random = AsyncMock(return_value=[])

        agent = AgentCore(amem=amem)
        agent.context_builder = mock_builder

        mock_thought = MagicMock()
        mock_thought.content = "test"
        mock_thought.metadata = {}
        mock_thought.thought_type = "mind_wandering"

        with (
            patch("clide.autonomy.thinker.Thinker") as mock_thinker_cls,
            patch("clide.core.agent.random") as mock_random,
        ):
            mock_random.choices.return_value = ["mind_wandering"]
            thinker_instance = MagicMock()
            thinker_instance.think = AsyncMock(return_value=(mock_thought, "neutral", 0.4))
            mock_thinker_cls.return_value = thinker_instance

            await agent.autonomous_think()

        call_kwargs = mock_builder.build.call_args[1]
        exclude = call_kwargs.get("exclude_types", [])
        assert "thought" in exclude
        assert "conversation" in exclude

    @pytest.mark.asyncio
    async def test_context_builder_does_not_exclude_conversation_when_no_fresh_convos(
        self,
    ) -> None:
        """'conversation' is NOT excluded when there are no fresh conversations."""
        from clide.core.context_builder import ContextResult

        mock_builder = MagicMock()
        mock_builder.build = AsyncMock(
            return_value=ContextResult(memory_text="", cross_mode_text="", memories_used=0)
        )

        amem = MagicMock()
        amem.remember = AsyncMock()
        amem.get_recent_by_type = AsyncMock(return_value=[])  # no conversations
        amem.get_random = AsyncMock(return_value=[])

        agent = AgentCore(amem=amem)
        agent.context_builder = mock_builder

        mock_thought = MagicMock()
        mock_thought.content = "test"
        mock_thought.metadata = {}
        mock_thought.thought_type = "mind_wandering"

        with (
            patch("clide.autonomy.thinker.Thinker") as mock_thinker_cls,
            patch("clide.core.agent.random") as mock_random,
        ):
            mock_random.choices.return_value = ["mind_wandering"]
            thinker_instance = MagicMock()
            thinker_instance.think = AsyncMock(return_value=(mock_thought, "neutral", 0.4))
            mock_thinker_cls.return_value = thinker_instance

            await agent.autonomous_think()

        call_kwargs = mock_builder.build.call_args[1]
        exclude = call_kwargs.get("exclude_types", [])
        assert "thought" in exclude
        assert "conversation" not in exclude


class TestConversationStorePersistence:
    """Tests for conversation store integration in AgentCore."""

    @pytest.fixture
    def store(self, tmp_path: Path) -> ConversationStore:
        return ConversationStore(db_path=tmp_path / "test.db")

    @pytest.mark.asyncio
    async def test_persists_user_message(self, store: ConversationStore) -> None:
        agent = AgentCore(conversation_store=store)
        with patch("clide.core.agent.stream_completion", side_effect=fake_stream_completion):
            async for _ in agent.process_message("hello"):
                pass
        messages = await store.get_recent()
        user_msgs = [m for m in messages if m["role"] == "user"]
        assert len(user_msgs) == 1
        assert user_msgs[0]["content"] == "hello"

    @pytest.mark.asyncio
    async def test_persists_assistant_message(self, store: ConversationStore) -> None:
        agent = AgentCore(conversation_store=store)
        with patch("clide.core.agent.stream_completion", side_effect=fake_stream_completion):
            async for _ in agent.process_message("hello"):
                pass
        messages = await store.get_recent()
        assistant_msgs = [m for m in messages if m["role"] == "assistant"]
        assert len(assistant_msgs) == 1
        assert assistant_msgs[0]["content"] == "Hello there!"

    @pytest.mark.asyncio
    async def test_history_loaded_from_store_on_first_message(
        self, store: ConversationStore
    ) -> None:
        # Pre-populate store
        await store.add_message("user", "old question")
        await store.add_message("assistant", "old answer")

        agent = AgentCore(conversation_store=store)
        assert agent.conversation_history == []

        with patch("clide.core.agent.stream_completion", side_effect=fake_stream_completion):
            async for _ in agent.process_message("new question"):
                pass

        # History should include old messages + new exchange
        assert len(agent.conversation_history) == 4
        assert agent.conversation_history[0]["content"] == "old question"
        assert agent.conversation_history[1]["content"] == "old answer"
        assert agent.conversation_history[2]["content"] == "new question"

    @pytest.mark.asyncio
    async def test_works_without_conversation_store(self) -> None:
        agent = AgentCore()
        chunks: list[str] = []
        with patch("clide.core.agent.stream_completion", side_effect=fake_stream_completion):
            async for chunk in agent.process_message("hi"):
                chunks.append(chunk)
        assert chunks == ["Hello", " there", "!"]
        assert len(agent.conversation_history) == 2

    @pytest.mark.asyncio
    async def test_clear_history_clears_store(self, store: ConversationStore) -> None:
        await store.add_message("user", "hello")
        agent = AgentCore(conversation_store=store)
        agent.conversation_history = [{"role": "user", "content": "hello"}]
        await agent.clear_history()
        assert agent.conversation_history == []
        messages = await store.get_recent()
        assert messages == []


class TestTimeAwareness:
    """Tests for time awareness features."""

    def test_born_at_stored(self) -> None:
        born = datetime.now(UTC)
        agent = AgentCore(born_at=born)
        assert agent.born_at is born

    def test_born_at_defaults_to_none(self) -> None:
        agent = AgentCore()
        assert agent.born_at is None

    def test_format_age_days(self) -> None:
        dt = datetime.now(UTC) - timedelta(days=5, hours=3)
        assert AgentCore._format_age(dt) == "5d ago"

    def test_format_age_hours(self) -> None:
        dt = datetime.now(UTC) - timedelta(hours=3, minutes=20)
        assert AgentCore._format_age(dt) == "3h ago"

    def test_format_age_minutes(self) -> None:
        dt = datetime.now(UTC) - timedelta(minutes=15)
        assert AgentCore._format_age(dt) == "15m ago"

    def test_format_age_just_now(self) -> None:
        dt = datetime.now(UTC) - timedelta(seconds=10)
        assert AgentCore._format_age(dt) == "just now"

    def test_format_age_naive_datetime(self) -> None:
        dt = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=2)
        assert AgentCore._format_age(dt) == "2d ago"


class TestProcessThoughtGoals:
    """Tests for _process_thought_goals method."""

    @pytest.mark.asyncio
    async def test_creates_goal_when_new_goal_in_metadata(self) -> None:
        goal_manager = MagicMock()
        goal_manager.get_active = AsyncMock(return_value=[])
        goal_manager.create = AsyncMock()

        agent = AgentCore(goal_manager=goal_manager)

        thought = MagicMock()
        thought.metadata = {"new_goal": "Learn about quantum computing"}

        await agent._process_thought_goals(thought)  # noqa: SLF001

        goal_manager.create.assert_awaited_once_with("Learn about quantum computing")

    @pytest.mark.asyncio
    async def test_respects_max_active_goals(self) -> None:
        goal_manager = MagicMock()
        # Return 5 active goals so we're at the max
        goal_manager.get_active = AsyncMock(return_value=[MagicMock() for _ in range(5)])
        goal_manager.create = AsyncMock()

        agent = AgentCore(goal_manager=goal_manager)

        thought = MagicMock()
        thought.metadata = {"new_goal": "Should not be created"}

        await agent._process_thought_goals(thought)  # noqa: SLF001

        goal_manager.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_updates_existing_goal(self) -> None:
        mock_goal = MagicMock()
        mock_goal.id = "goal-123"
        mock_goal.description = "Learn about astronomy"

        goal_manager = MagicMock()
        goal_manager.get_active = AsyncMock(return_value=[mock_goal])
        goal_manager.update = AsyncMock()

        agent = AgentCore(goal_manager=goal_manager)

        import json

        updates = [
            {
                "description": "Learn about astronomy",
                "progress": 0.5,
                "status": "completed",
                "reason": "Discussed star formation",
            }
        ]
        thought = MagicMock()
        thought.metadata = {"goal_updates": json.dumps(updates)}

        await agent._process_thought_goals(thought)  # noqa: SLF001

        from clide.autonomy.models import GoalStatus

        goal_manager.update.assert_awaited_once_with(
            "goal-123",
            progress=0.5,
            status=GoalStatus.COMPLETED,
            notes="Discussed star formation",
        )

    @pytest.mark.asyncio
    async def test_no_error_when_goal_manager_is_none(self) -> None:
        agent = AgentCore()  # No goal_manager
        assert agent.goal_manager is None

        thought = MagicMock()
        thought.metadata = {"new_goal": "Should not crash"}

        # Should not raise
        await agent._process_thought_goals(thought)  # noqa: SLF001

    @pytest.mark.asyncio
    async def test_post_response_nudges_goal_progress(self) -> None:
        mock_goal = MagicMock()
        mock_goal.id = "goal-456"
        mock_goal.description = "Learn about machine learning algorithms"
        mock_goal.progress = 0.2

        goal_manager = MagicMock()
        goal_manager.get_active = AsyncMock(return_value=[mock_goal])
        goal_manager.update = AsyncMock()

        agent = AgentCore(goal_manager=goal_manager)

        # Conversation about machine learning (matches "machine", "learning", "algorithms")
        await agent._post_response_tasks(
            "Tell me about machine learning algorithms",
            "Machine learning algorithms include decision trees and neural networks.",
        )

        goal_manager.update.assert_awaited_once_with(
            "goal-456",
            progress=0.25,  # 0.2 + 0.05
        )


def _make_tool_response(
    tool_calls: list[tuple[str, str, str]] | None = None,
    content: str | None = None,
) -> MagicMock:
    """Create a mock LLM response.

    Args:
        tool_calls: list of (name, arguments_json, call_id) tuples, or None for text.
        content: text content for non-tool responses.
    """
    mock = MagicMock()
    choice = MagicMock()
    mock.choices = [choice]

    if tool_calls:
        choice.finish_reason = "tool_calls"
        tc_mocks = []
        for name, args, call_id in tool_calls:
            tc = MagicMock()
            tc.function.name = name
            tc.function.arguments = args
            tc.id = call_id
            tc_mocks.append(tc)
        choice.message.tool_calls = tc_mocks
        choice.message.model_dump.return_value = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": cid, "function": {"name": n, "arguments": a}, "type": "function"}
                for n, a, cid in tool_calls
            ],
        }
    else:
        choice.finish_reason = "stop"
        choice.message.tool_calls = None
        choice.message.content = content or ""

    return mock


def _make_mock_registry(
    tools: list[dict[str, object]] | None = None,
    execute_return: ToolResult | None = None,
) -> MagicMock:
    """Create a mock ToolRegistry."""
    registry = MagicMock()
    registry.get_tool_definitions_for_llm.return_value = tools or [
        {
            "type": "function",
            "function": {"name": "web_search", "description": "Search", "parameters": {}},
        }
    ]
    registry.execute_tool = AsyncMock(
        return_value=execute_return
        or ToolResult(call_id="call_123", result={"data": "results"}, success=True)
    )
    return registry


class TestToolRegistry:
    """Tests for tool registry integration in AgentCore."""

    def test_tool_registry_stored(self) -> None:
        registry = MagicMock()
        agent = AgentCore(tool_registry=registry)
        assert agent.tool_registry is registry

    def test_tool_registry_defaults_to_none(self) -> None:
        agent = AgentCore()
        assert agent.tool_registry is None

    def test_set_tool_event_callback(self) -> None:
        agent = AgentCore()
        cb = MagicMock()
        agent.set_tool_event_callback(cb)
        assert agent._tool_event_callback is cb  # noqa: SLF001


class TestProcessMessageWithTools:
    """Tests for process_message with tool registry."""

    @pytest.mark.asyncio
    async def test_uses_tools_when_available(self) -> None:
        registry = _make_mock_registry()
        agent = AgentCore(tool_registry=registry)

        text_response = _make_tool_response(content="Here are the results.")
        with patch("clide.core.agent.complete_with_tools", new_callable=AsyncMock) as mock_cwt:
            mock_cwt.return_value = text_response
            chunks: list[str] = []
            async for chunk in agent.process_message("search for cats"):
                chunks.append(chunk)

        assert chunks == ["Here are the results."]
        mock_cwt.assert_awaited()

    @pytest.mark.asyncio
    async def test_streams_without_tools(self) -> None:
        agent = AgentCore()  # No tool_registry
        with patch("clide.core.agent.stream_completion", side_effect=fake_stream_completion):
            chunks: list[str] = []
            async for chunk in agent.process_message("hi"):
                chunks.append(chunk)
        assert chunks == ["Hello", " there", "!"]


class TestProcessWithTools:
    """Tests for agent_step() tool-calling behavior (formerly _process_with_tools)."""

    @pytest.mark.asyncio
    async def test_executes_tool_and_returns_text(self) -> None:
        from clide.core.agent_events import TextChunkEvent

        registry = _make_mock_registry()
        agent = AgentCore(tool_registry=registry)
        # Force CONVERSING state so WORKING transition is valid
        agent.state_machine.transition(AgentState.CONVERSING, "test")

        tool_response = _make_tool_response(
            tool_calls=[("web_search", '{"query": "test"}', "call_123")]
        )
        text_response = _make_tool_response(content="Here are the results.")

        with patch("clide.core.agent.complete_with_tools", new_callable=AsyncMock) as mock_cwt:
            mock_cwt.side_effect = [tool_response, text_response]
            events = []
            async for event in agent.agent_step(
                messages=[{"role": "user", "content": "search"}],
                tools=registry.get_tool_definitions_for_llm(),
                session_id="test-session",
                mode="chat",
            ):
                events.append(event)

        text_events = [e for e in events if isinstance(e, TextChunkEvent) and e.done]
        assert text_events[-1].content == "Here are the results."
        registry.execute_tool.assert_awaited_once_with("web_search", {"query": "test"})

    @pytest.mark.asyncio
    async def test_max_iterations_safety(self) -> None:
        from clide.core.agent_events import TextChunkEvent

        registry = _make_mock_registry()
        agent = AgentCore(tool_registry=registry)
        agent.state_machine.transition(AgentState.CONVERSING, "test")

        # Always return tool calls — should stop at phase_size * max_phases
        # Use small values for test speed
        call_counter = 0

        def make_unique_tool_response() -> MagicMock:
            nonlocal call_counter
            call_counter += 1
            return _make_tool_response(
                tool_calls=[("web_search", f'{{"q": "x{call_counter}"}}', f"call_{call_counter}")]
            )

        checkpoint_response = MagicMock()
        checkpoint_response.choices = [MagicMock()]
        checkpoint_response.choices[0].message.content = "Checkpoint summary"
        checkpoint_response.usage = MagicMock(prompt_tokens=10, completion_tokens=5)

        with patch("clide.core.agent.complete_with_tools", new_callable=AsyncMock) as mock_cwt:
            # agent_step uses complete_with_tools for checkpoints too
            mock_cwt.side_effect = lambda *a, **kw: make_unique_tool_response()
            events = []
            async for event in agent.agent_step(
                messages=[{"role": "user", "content": "search"}],
                tools=registry.get_tool_definitions_for_llm(),
                session_id="test-session",
                mode="chat",
                phase_size=3,
                max_phases=2,
            ):
                events.append(event)

        text_events = [e for e in events if isinstance(e, TextChunkEvent) and e.done]
        assert text_events
        result = text_events[-1].content
        assert "extensive research" in result.lower() or "tool" in result.lower()
        # phase_size * max_phases = 6 tool calls + 1 checkpoint call = 7 total
        assert mock_cwt.await_count == 7

    @pytest.mark.asyncio
    async def test_tool_event_callback_called(self) -> None:
        from clide.core.agent_events import StateChangeEvent, TextChunkEvent, ToolCallEvent, ToolResultEvent

        registry = _make_mock_registry()
        agent = AgentCore(tool_registry=registry)
        agent.state_machine.transition(AgentState.CONVERSING, "test")

        tool_response = _make_tool_response(
            tool_calls=[("web_search", '{"query": "test"}', "call_123")]
        )
        text_response = _make_tool_response(content="Done.")

        with patch("clide.core.agent.complete_with_tools", new_callable=AsyncMock) as mock_cwt:
            mock_cwt.side_effect = [tool_response, text_response]
            events = []
            async for event in agent.agent_step(
                messages=[{"role": "user", "content": "search"}],
                tools=registry.get_tool_definitions_for_llm(),
                session_id="test-session",
                mode="chat",
            ):
                events.append(event)

        # Verify that state change, tool call, and tool result events were yielded
        state_events = [e for e in events if isinstance(e, StateChangeEvent)]
        tool_call_events = [e for e in events if isinstance(e, ToolCallEvent)]
        tool_result_events = [e for e in events if isinstance(e, ToolResultEvent)]

        assert any(e.new_state == "working" for e in state_events)
        assert len(tool_call_events) == 1
        assert tool_call_events[0].tool_name == "web_search"
        assert tool_call_events[0].call_id == "call_123"
        assert len(tool_result_events) == 1
        assert tool_result_events[0].call_id == "call_123"
        assert tool_result_events[0].success is True

    @pytest.mark.asyncio
    async def test_callback_failure_does_not_break_loop(self) -> None:
        """agent_step yields events; consumers can ignore them without breaking the loop."""
        from clide.core.agent_events import TextChunkEvent

        registry = _make_mock_registry()
        agent = AgentCore(tool_registry=registry)
        agent.state_machine.transition(AgentState.CONVERSING, "test")

        tool_response = _make_tool_response(
            tool_calls=[("web_search", '{"query": "test"}', "call_123")]
        )
        text_response = _make_tool_response(content="Done.")

        with patch("clide.core.agent.complete_with_tools", new_callable=AsyncMock) as mock_cwt:
            mock_cwt.side_effect = [tool_response, text_response]
            events = []
            async for event in agent.agent_step(
                messages=[{"role": "user", "content": "search"}],
                tools=registry.get_tool_definitions_for_llm(),
                session_id="test-session",
                mode="chat",
            ):
                events.append(event)

        text_events = [e for e in events if isinstance(e, TextChunkEvent) and e.done]
        assert text_events[-1].content == "Done."

    @pytest.mark.asyncio
    async def test_no_tools_returns_empty_definitions(self) -> None:
        registry = MagicMock()
        registry.get_tool_definitions_for_llm.return_value = []
        agent = AgentCore(tool_registry=registry)

        # With empty tools, should fall through to streaming path
        with patch("clide.core.agent.stream_completion", side_effect=fake_stream_completion):
            chunks: list[str] = []
            async for chunk in agent.process_message("hi"):
                chunks.append(chunk)
        assert chunks == ["Hello", " there", "!"]


class TestPhasedToolExecution:
    """Tests for phased tool execution with checkpoints and dedup via agent_step()."""

    @pytest.mark.asyncio
    async def test_phase_checkpoint_triggered(self) -> None:
        """After phase_size tool calls, a checkpoint is generated."""
        from clide.core.agent_events import CheckpointEvent, TextChunkEvent

        registry = _make_mock_registry()
        agent = AgentCore(tool_registry=registry)
        agent.state_machine.transition(AgentState.CONVERSING, "test")

        # After phase_size=3 tool calls, checkpoint fires; then text after 1 more
        responses: list[MagicMock] = []
        # Phase 1: 3 tool calls
        for i in range(3):
            responses.append(
                _make_tool_response(tool_calls=[("web_search", f'{{"q": "q{i}"}}', f"call_{i}")])
            )
        # Checkpoint (phase 2 start): also handled by complete_with_tools in agent_step
        checkpoint_response = _make_tool_response(content="Progress checkpoint")
        responses.append(checkpoint_response)
        # Phase 2: 1 tool call then text
        responses.append(_make_tool_response(tool_calls=[("web_search", '{"q": "q3"}', "call_3")]))
        responses.append(_make_tool_response(content="Final answer after phases."))

        with patch("clide.core.agent.complete_with_tools", new_callable=AsyncMock) as mock_cwt:
            mock_cwt.side_effect = responses
            events = []
            async for event in agent.agent_step(
                messages=[{"role": "user", "content": "search"}],
                tools=registry.get_tool_definitions_for_llm(),
                session_id="test-session",
                mode="chat",
                phase_size=3,
                max_phases=3,
            ):
                events.append(event)

        text_events = [e for e in events if isinstance(e, TextChunkEvent) and e.done]
        assert text_events[-1].content == "Final answer after phases."
        # Checkpoint event should have been yielded once (after phase 1)
        checkpoint_events = [e for e in events if isinstance(e, CheckpointEvent)]
        assert len(checkpoint_events) == 1

    @pytest.mark.asyncio
    async def test_dedup_detection(self) -> None:
        """Same tool+args called twice => second is skipped with DUPLICATE."""
        from clide.core.agent_events import TextChunkEvent

        registry = _make_mock_registry()
        agent = AgentCore(tool_registry=registry)
        agent.state_machine.transition(AgentState.CONVERSING, "test")

        # First call: web_search with {"q": "cats"}
        tool_response_1 = _make_tool_response(
            tool_calls=[("web_search", '{"q": "cats"}', "call_1")]
        )
        # Second call: SAME tool+args (duplicate)
        tool_response_2 = _make_tool_response(
            tool_calls=[("web_search", '{"q": "cats"}', "call_2")]
        )
        text_response = _make_tool_response(content="Done.")

        messages: list[dict[str, Any]] = [{"role": "user", "content": "search cats"}]
        with patch("clide.core.agent.complete_with_tools", new_callable=AsyncMock) as mock_cwt:
            mock_cwt.side_effect = [tool_response_1, tool_response_2, text_response]
            events = []
            async for event in agent.agent_step(
                messages=messages,
                tools=registry.get_tool_definitions_for_llm(),
                session_id="test-session",
                mode="chat",
            ):
                events.append(event)

        text_events = [e for e in events if isinstance(e, TextChunkEvent) and e.done]
        assert text_events[-1].content == "Done."
        # Tool should only be EXECUTED once (first call), duplicate skipped
        assert registry.execute_tool.await_count == 1

        # Check that a DUPLICATE message was added for the second call
        tool_messages = [m for m in messages if m.get("role") == "tool"]
        dup_messages = [m for m in tool_messages if "DUPLICATE" in m.get("content", "")]
        assert len(dup_messages) == 1
        assert "web_search" in dup_messages[0]["content"]

    @pytest.mark.asyncio
    async def test_dedup_different_args_both_execute(self) -> None:
        """Same tool with different args => both execute (not duplicates)."""
        from clide.core.agent_events import TextChunkEvent

        registry = _make_mock_registry()
        agent = AgentCore(tool_registry=registry)
        agent.state_machine.transition(AgentState.CONVERSING, "test")

        tool_response_1 = _make_tool_response(
            tool_calls=[("web_search", '{"q": "cats"}', "call_1")]
        )
        tool_response_2 = _make_tool_response(
            tool_calls=[("web_search", '{"q": "dogs"}', "call_2")]
        )
        text_response = _make_tool_response(content="Both done.")

        with patch("clide.core.agent.complete_with_tools", new_callable=AsyncMock) as mock_cwt:
            mock_cwt.side_effect = [tool_response_1, tool_response_2, text_response]
            events = []
            async for event in agent.agent_step(
                messages=[{"role": "user", "content": "search"}],
                tools=registry.get_tool_definitions_for_llm(),
                session_id="test-session",
                mode="chat",
            ):
                events.append(event)

        text_events = [e for e in events if isinstance(e, TextChunkEvent) and e.done]
        assert text_events[-1].content == "Both done."
        # Both calls should be executed (different args)
        assert registry.execute_tool.await_count == 2

    @pytest.mark.asyncio
    async def test_max_phases_exhausted(self) -> None:
        """When LLM always returns tool calls, loop stops at phase_size * max_phases."""
        from clide.core.agent_events import TextChunkEvent

        registry = _make_mock_registry()
        agent = AgentCore(tool_registry=registry)
        agent.state_machine.transition(AgentState.CONVERSING, "test")

        call_counter = 0

        def make_unique_tool_response() -> MagicMock:
            nonlocal call_counter
            call_counter += 1
            r = _make_tool_response(
                tool_calls=[("web_search", f'{{"q": "x{call_counter}"}}', f"call_{call_counter}")]
            )
            r.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
            return r

        with patch("clide.core.agent.complete_with_tools", new_callable=AsyncMock) as mock_cwt:
            mock_cwt.side_effect = lambda *a, **kw: make_unique_tool_response()
            events = []
            async for event in agent.agent_step(
                messages=[{"role": "user", "content": "search"}],
                tools=registry.get_tool_definitions_for_llm(),
                session_id="test-session",
                mode="chat",
                phase_size=2,
                max_phases=2,
            ):
                events.append(event)

        # Should exhaust all phases and emit exhaustion message
        text_events = [e for e in events if isinstance(e, TextChunkEvent) and e.done]
        assert text_events
        assert "extensive research" in text_events[-1].content.lower()
        # phase_size * max_phases = 4 tool calls + 1 checkpoint call = 5 total
        assert mock_cwt.await_count == 5

    @pytest.mark.asyncio
    async def test_phase_size_configurable(self) -> None:
        """Verify phase_size parameter controls when checkpoints fire."""
        from clide.core.agent_events import CheckpointEvent

        registry = _make_mock_registry()
        agent = AgentCore(tool_registry=registry)
        agent.state_machine.transition(AgentState.CONVERSING, "test")

        call_counter = 0

        def make_unique_tool_response() -> MagicMock:
            nonlocal call_counter
            call_counter += 1
            r = _make_tool_response(
                tool_calls=[("web_search", f'{{"q": "x{call_counter}"}}', f"call_{call_counter}")]
            )
            r.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
            return r

        checkpoint_response = _make_tool_response(content="Checkpoint")
        checkpoint_response.usage = MagicMock(prompt_tokens=10, completion_tokens=5)

        # phase_size=5, max_phases=2 => total 10 tool calls, 1 checkpoint
        with patch("clide.core.agent.complete_with_tools", new_callable=AsyncMock) as mock_cwt:
            # The checkpoint call (at phase 2 start) returns checkpoint_response,
            # all other calls return unique tool responses
            checkpoint_call_idx = 5  # after 5 tool calls in phase 1
            call_idx = [0]

            def side_effect(*a: object, **kw: object) -> MagicMock:
                call_idx[0] += 1
                if call_idx[0] == checkpoint_call_idx + 1:
                    return checkpoint_response
                return make_unique_tool_response()

            mock_cwt.side_effect = side_effect
            events = []
            async for event in agent.agent_step(
                messages=[{"role": "user", "content": "search"}],
                tools=registry.get_tool_definitions_for_llm(),
                session_id="test-session",
                mode="chat",
                phase_size=5,
                max_phases=2,
            ):
                events.append(event)

        # 1 checkpoint event (after phase 1, before phase 2)
        checkpoint_events = [e for e in events if isinstance(e, CheckpointEvent)]
        assert len(checkpoint_events) == 1
        # Total calls = 5 (phase1 tools) + 1 (checkpoint) + 5 (phase2 tools) = 11
        assert mock_cwt.await_count == 11

    @pytest.mark.asyncio
    async def test_tool_call_count_tracks_correctly(self) -> None:
        """Verify tool_call_count increments per actual tool execution, not per iteration."""
        from clide.core.agent_events import TextChunkEvent

        registry = _make_mock_registry()
        agent = AgentCore(tool_registry=registry)
        agent.state_machine.transition(AgentState.CONVERSING, "test")

        # 2 tool calls then text — all unique
        responses = [
            _make_tool_response(tool_calls=[("web_search", '{"q": "first"}', "call_1")]),
            _make_tool_response(tool_calls=[("web_search", '{"q": "second"}', "call_2")]),
            _make_tool_response(content="Final."),
        ]

        with patch("clide.core.agent.complete_with_tools", new_callable=AsyncMock) as mock_cwt:
            mock_cwt.side_effect = responses
            events = []
            async for event in agent.agent_step(
                messages=[{"role": "user", "content": "search"}],
                tools=registry.get_tool_definitions_for_llm(),
                session_id="test-session",
                mode="chat",
                phase_size=10,
                max_phases=3,
            ):
                events.append(event)

        text_events = [e for e in events if isinstance(e, TextChunkEvent) and e.done]
        assert text_events[-1].content == "Final."
        # Both tool calls executed (2 unique)
        assert registry.execute_tool.await_count == 2

    @pytest.mark.asyncio
    async def test_checkpoint_failure_continues(self) -> None:
        """If checkpoint generation fails, the loop continues."""
        from clide.core.agent_events import TextChunkEvent

        registry = _make_mock_registry()
        agent = AgentCore(tool_registry=registry)
        agent.state_machine.transition(AgentState.CONVERSING, "test")

        call_counter = 0

        def make_unique_tool_response() -> MagicMock:
            nonlocal call_counter
            call_counter += 1
            r = _make_tool_response(
                tool_calls=[("web_search", f'{{"q": "x{call_counter}"}}', f"call_{call_counter}")]
            )
            r.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
            return r

        # phase_size=2, max_phases=2 => 4 tool calls total
        # The checkpoint call (at index 3, i.e. the 3rd call overall) raises an exception
        checkpoint_call_idx = 2  # 0-indexed: calls 0,1 are phase1 tools, call 2 is checkpoint

        call_idx = [0]

        def side_effect(*a: object, **kw: object) -> MagicMock:
            idx = call_idx[0]
            call_idx[0] += 1
            if idx == checkpoint_call_idx:
                raise RuntimeError("LLM down")
            return make_unique_tool_response()

        with patch("clide.core.agent.complete_with_tools", new_callable=AsyncMock) as mock_cwt:
            mock_cwt.side_effect = side_effect
            events = []
            async for event in agent.agent_step(
                messages=[{"role": "user", "content": "search"}],
                tools=registry.get_tool_definitions_for_llm(),
                session_id="test-session",
                mode="chat",
                phase_size=2,
                max_phases=2,
            ):
                events.append(event)

        # Should still complete (exhaust phases even with checkpoint failure)
        text_events = [e for e in events if isinstance(e, TextChunkEvent) and e.done]
        assert text_events
        assert "extensive research" in text_events[-1].content.lower()

    @pytest.mark.asyncio
    async def test_default_phase_attributes(self) -> None:
        """Verify AgentCore has default phase attributes."""
        agent = AgentCore()
        assert agent.tool_phase_size == 10
        assert agent.tool_max_phases == 3


class TestAutonomousThinkWithTools:
    """Tests for tool support in autonomous thinking (two-phase approach)."""

    @pytest.mark.asyncio
    async def test_autonomous_think_with_tools(self) -> None:
        """Phase 1 runs when tool_registry has tools, and results are passed to thinker."""
        from clide.core.agent_events import TextChunkEvent

        registry = _make_mock_registry()
        agent = AgentCore(tool_registry=registry)

        mock_thought = MagicMock()
        mock_thought.content = "I learned something from tools"
        mock_thought.metadata = {"topic": "research", "follow_up": ""}
        mock_thought.thought_type = "goal_oriented"

        captured_kwargs: dict[str, object] = {}

        async def capturing_think(**kwargs: object) -> tuple[MagicMock, str, float]:
            captured_kwargs.update(kwargs)
            return mock_thought, "curious", 0.8

        # Phase 1: agent_step yields tool results as TextChunkEvent
        async def mock_agent_step(*args: object, **kwargs: object) -> AsyncIterator[object]:
            yield TextChunkEvent(content="Tool result: some useful data from web search", done=True)

        with (
            patch("clide.autonomy.thinker.Thinker") as mock_thinker_cls,
            patch.object(agent, "agent_step", side_effect=mock_agent_step) as mock_step,
            patch("clide.core.agent.random") as mock_random,
        ):
            mock_random.choices.return_value = ["goal_oriented"]
            thinker_instance = MagicMock()
            thinker_instance.think = capturing_think
            mock_thinker_cls.return_value = thinker_instance

            result = await agent.autonomous_think()

        assert result is not None
        assert result[0] == "I learned something from tools"

        # Phase 1 should have been called
        mock_step.assert_called_once()

        # Tool results should be incorporated into thinker context.
        # If thinker accepts tool_results_context param, it's passed directly;
        # otherwise it's appended to tools_context as a fallback.
        tools_ctx = str(captured_kwargs.get("tools_context", ""))
        has_direct = captured_kwargs.get("tool_results_context") is not None
        assert has_direct or "Tool results from exploration:" in tools_ctx

        # Thought metadata should record tool usage
        assert mock_thought.metadata["used_tools"] == "true"
        assert "some useful data" in mock_thought.metadata["tool_results_preview"]

    @pytest.mark.asyncio
    async def test_autonomous_think_without_tools(self) -> None:
        """Phase 1 is skipped when no tool_registry is set."""
        agent = AgentCore()  # No tool_registry

        mock_thought = MagicMock()
        mock_thought.content = "standalone thought"
        mock_thought.metadata = {"topic": "", "follow_up": ""}

        captured_kwargs: dict[str, object] = {}

        async def capturing_think(**kwargs: object) -> tuple[MagicMock, str, float]:
            captured_kwargs.update(kwargs)
            return mock_thought, "neutral", 0.5

        with patch("clide.autonomy.thinker.Thinker") as mock_thinker_cls:
            thinker_instance = MagicMock()
            thinker_instance.think = capturing_think
            mock_thinker_cls.return_value = thinker_instance

            result = await agent.autonomous_think()

        assert result is not None
        # tool_results_context should NOT be passed (Phase 1 skipped, empty string)
        assert "tool_results_context" not in captured_kwargs
        # tools_context should not have tool exploration results
        tools_ctx = str(captured_kwargs.get("tools_context", ""))
        assert "Tool results from exploration:" not in tools_ctx
        # No tool metadata should be set
        assert "used_tools" not in mock_thought.metadata

    @pytest.mark.asyncio
    async def test_autonomous_think_tool_failure_continues(self) -> None:
        """Phase 1 failure does not block Phase 2 thinking."""
        registry = _make_mock_registry()
        agent = AgentCore(tool_registry=registry)

        mock_thought = MagicMock()
        mock_thought.content = "thought despite tool failure"
        mock_thought.metadata = {"topic": "", "follow_up": ""}

        captured_kwargs: dict[str, object] = {}

        async def capturing_think(**kwargs: object) -> tuple[MagicMock, str, float]:
            captured_kwargs.update(kwargs)
            return mock_thought, "neutral", 0.5

        # Phase 1: agent_step raises an exception
        async def mock_agent_step_fail(*args: object, **kwargs: object) -> AsyncIterator[object]:
            raise RuntimeError("MCP server down")
            yield  # make it an async generator

        with (
            patch("clide.autonomy.thinker.Thinker") as mock_thinker_cls,
            patch.object(agent, "agent_step", side_effect=mock_agent_step_fail),
        ):
            thinker_instance = MagicMock()
            thinker_instance.think = capturing_think
            mock_thinker_cls.return_value = thinker_instance

            result = await agent.autonomous_think()

        # Phase 2 should still succeed
        assert result is not None
        assert result[0] == "thought despite tool failure"
        # tool_results_context should NOT be passed (Phase 1 failed, empty string)
        assert "tool_results_context" not in captured_kwargs
        # tools_context should not have tool exploration results
        tools_ctx = str(captured_kwargs.get("tools_context", ""))
        assert "Tool results from exploration:" not in tools_ctx
        # No tool metadata should be set
        assert "used_tools" not in mock_thought.metadata


class TestAntiTunnelVision:
    """Tests for topic tracking and diversity enforcement."""

    @pytest.mark.asyncio
    async def test_topic_tracking(self) -> None:
        """Verify _recent_topics is updated after thinking."""
        agent = AgentCore()

        mock_thought = MagicMock()
        mock_thought.content = "Thinking about stars"
        mock_thought.metadata = {"topic": "astronomy", "follow_up": ""}

        with patch("clide.autonomy.thinker.Thinker") as mock_thinker_cls:
            thinker_instance = MagicMock()
            thinker_instance.think = AsyncMock(return_value=(mock_thought, "curious", 0.7))
            mock_thinker_cls.return_value = thinker_instance

            await agent.autonomous_think()

        assert "astronomy" in agent._recent_topics

    @pytest.mark.asyncio
    async def test_topic_history_capped(self) -> None:
        """Verify topic history is capped at _topic_history_size."""
        agent = AgentCore()
        agent._topic_history_size = 3

        topics = ["stars", "music", "food", "code"]
        for topic in topics:
            mock_thought = MagicMock()
            mock_thought.content = f"Thinking about {topic}"
            mock_thought.metadata = {"topic": topic, "follow_up": ""}

            with patch("clide.autonomy.thinker.Thinker") as mock_thinker_cls:
                thinker_instance = MagicMock()
                thinker_instance.think = AsyncMock(return_value=(mock_thought, "curious", 0.5))
                mock_thinker_cls.return_value = thinker_instance

                await agent.autonomous_think()

        assert len(agent._recent_topics) == 3
        assert agent._recent_topics == ["music", "food", "code"]

    @pytest.mark.asyncio
    async def test_diversity_instruction_triggered(self) -> None:
        """When same topic appears 3+ times, diversity text is prepended."""
        agent = AgentCore()
        agent._recent_topics = ["ai", "ai", "ai"]

        captured_kwargs: dict[str, object] = {}

        mock_thought = MagicMock()
        mock_thought.content = "Something different"
        mock_thought.metadata = {"topic": "nature", "follow_up": ""}
        mock_thought.thought_type = "goal_oriented"

        async def capturing_think(**kwargs: object) -> tuple[MagicMock, str, float]:
            captured_kwargs.update(kwargs)
            return mock_thought, "curious", 0.5

        with (
            patch("clide.autonomy.thinker.Thinker") as mock_thinker_cls,
            patch("clide.core.agent.random") as mock_random,
        ):
            mock_random.choices.return_value = ["goal_oriented"]
            thinker_instance = MagicMock()
            thinker_instance.think = capturing_think
            mock_thinker_cls.return_value = thinker_instance

            await agent.autonomous_think()

        thought_history = str(captured_kwargs.get("thought_history", ""))
        assert "IMPORTANT" in thought_history
        assert "ai" in thought_history.lower()
        assert "MUST think about something completely different" in thought_history

    @pytest.mark.asyncio
    async def test_soft_nudge_at_two_repeats(self) -> None:
        """When same topic appears 2 times, a soft nudge is added."""
        agent = AgentCore()
        agent._recent_topics = ["ai", "ai", "music"]

        captured_kwargs: dict[str, object] = {}

        mock_thought = MagicMock()
        mock_thought.content = "Thinking"
        mock_thought.metadata = {"topic": "poetry", "follow_up": ""}
        mock_thought.thought_type = "goal_oriented"

        async def capturing_think(**kwargs: object) -> tuple[MagicMock, str, float]:
            captured_kwargs.update(kwargs)
            return mock_thought, "curious", 0.5

        with (
            patch("clide.autonomy.thinker.Thinker") as mock_thinker_cls,
            patch("clide.core.agent.random") as mock_random,
        ):
            mock_random.choices.return_value = ["goal_oriented"]
            thinker_instance = MagicMock()
            thinker_instance.think = capturing_think
            mock_thinker_cls.return_value = thinker_instance

            await agent.autonomous_think()

        thought_history = str(captured_kwargs.get("thought_history", ""))
        assert "Consider exploring a different topic" in thought_history

    @pytest.mark.asyncio
    async def test_no_diversity_instruction_with_varied_topics(self) -> None:
        """No diversity instruction when topics are varied."""
        agent = AgentCore()
        agent._recent_topics = ["ai", "music", "food"]

        captured_kwargs: dict[str, object] = {}

        mock_thought = MagicMock()
        mock_thought.content = "Thinking"
        mock_thought.metadata = {"topic": "art", "follow_up": ""}

        async def capturing_think(**kwargs: object) -> tuple[MagicMock, str, float]:
            captured_kwargs.update(kwargs)
            return mock_thought, "curious", 0.5

        with patch("clide.autonomy.thinker.Thinker") as mock_thinker_cls:
            thinker_instance = MagicMock()
            thinker_instance.think = capturing_think
            mock_thinker_cls.return_value = thinker_instance

            await agent.autonomous_think()

        thought_history = str(captured_kwargs.get("thought_history", ""))
        assert "IMPORTANT" not in thought_history
        assert "Consider exploring" not in thought_history
