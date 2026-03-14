"""Tests for the agent core."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clide.api.schemas import AgentState
from clide.core.agent import AgentCore


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

    def test_clear_history(self) -> None:
        agent = AgentCore()
        agent.conversation_history = [{"role": "user", "content": "test"}]
        agent.clear_history()
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
        assert "User said: hello" in call_args[0][0]
        assert "Hello there!" in call_args[0][0]
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

        with patch("clide.autonomy.thinker.Thinker") as mock_thinker_cls:
            thinker_instance = MagicMock()
            thinker_instance.think = AsyncMock(return_value=(mock_thought, "curious", 0.7))
            mock_thinker_cls.return_value = thinker_instance

            result = await agent.autonomous_think()

        assert result is not None
        assert result == ("I wonder about the stars", "curious", 0.7)

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

        captured_kwargs: dict[str, object] = {}

        async def capturing_think(**kwargs: object) -> tuple[MagicMock, str, float]:
            captured_kwargs.update(kwargs)
            return mock_thought, "neutral", 0.5

        with patch("clide.autonomy.thinker.Thinker") as mock_thinker_cls:
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
        goal_manager.get_active = AsyncMock(return_value=[mock_goal])

        agent = AgentCore(goal_manager=goal_manager)

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

        goals_ctx = str(captured_kwargs.get("goals_context", ""))
        assert "Learn about astronomy" in goals_ctx

    @pytest.mark.asyncio
    async def test_gathers_thought_history(self) -> None:
        past_thought = _make_zettel_mock(
            content="Autonomous thought: I was pondering the nature of consciousness",
            metadata={"type": "thought"},
        )
        amem = MagicMock()
        amem.recall = AsyncMock(return_value=[past_thought])
        amem.remember = AsyncMock()

        agent = AgentCore(amem=amem)

        mock_thought = MagicMock()
        mock_thought.content = "new thought"
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

        thought_hist = str(captured_kwargs.get("thought_history", ""))
        assert "pondering the nature of consciousness" in thought_hist

    @pytest.mark.asyncio
    async def test_uses_follow_up_from_previous_thought_as_query(self) -> None:
        """If a previous thought has a follow_up, use it as the recall query."""
        past_thought = _make_zettel_mock(
            content="Autonomous thought: pondering",
            metadata={"type": "thought", "follow_up": "explore fractals", "topic": "math"},
        )
        amem = MagicMock()
        amem.recall = AsyncMock(return_value=[past_thought])
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

        # The second recall call should use "explore fractals" as query
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

        with patch("clide.autonomy.thinker.Thinker") as mock_thinker_cls:
            thinker_instance = MagicMock()
            thinker_instance.think = AsyncMock(return_value=(mock_thought, "neutral", 0.5))
            mock_thinker_cls.return_value = thinker_instance

            result = await agent.autonomous_think()

        assert result is not None
        assert result == ("standalone thought", "neutral", 0.5)

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
