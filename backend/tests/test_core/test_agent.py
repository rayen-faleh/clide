"""Tests for the agent core."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
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
        mock_goal.created_at = datetime.now(UTC)
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
        amem.get_recent_by_type = AsyncMock(return_value=[past_thought])
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
    """Tests for _process_with_tools method."""

    @pytest.mark.asyncio
    async def test_executes_tool_and_returns_text(self) -> None:
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
            result = await agent._process_with_tools(  # noqa: SLF001
                [{"role": "user", "content": "search"}],
                registry.get_tool_definitions_for_llm(),
            )

        assert result == "Here are the results."
        registry.execute_tool.assert_awaited_once_with("web_search", {"query": "test"})

    @pytest.mark.asyncio
    async def test_max_iterations_safety(self) -> None:
        registry = _make_mock_registry()
        agent = AgentCore(tool_registry=registry)
        agent.state_machine.transition(AgentState.CONVERSING, "test")

        # Always return tool calls — should stop at 10
        tool_response = _make_tool_response(tool_calls=[("web_search", '{"q": "x"}', "call_1")])

        with patch("clide.core.agent.complete_with_tools", new_callable=AsyncMock) as mock_cwt:
            mock_cwt.return_value = tool_response
            result = await agent._process_with_tools(  # noqa: SLF001
                [{"role": "user", "content": "search"}],
                registry.get_tool_definitions_for_llm(),
            )

        assert "tool loop" in result.lower()
        assert mock_cwt.await_count == 10

    @pytest.mark.asyncio
    async def test_tool_event_callback_called(self) -> None:
        registry = _make_mock_registry()
        agent = AgentCore(tool_registry=registry)
        agent.state_machine.transition(AgentState.CONVERSING, "test")

        callback = AsyncMock()
        agent.set_tool_event_callback(callback)

        tool_response = _make_tool_response(
            tool_calls=[("web_search", '{"query": "test"}', "call_123")]
        )
        text_response = _make_tool_response(content="Done.")

        with patch("clide.core.agent.complete_with_tools", new_callable=AsyncMock) as mock_cwt:
            mock_cwt.side_effect = [tool_response, text_response]
            await agent._process_with_tools(  # noqa: SLF001
                [{"role": "user", "content": "search"}],
                registry.get_tool_definitions_for_llm(),
            )

        callback.assert_awaited_once()
        event = callback.call_args[0][0]
        assert event["tool_name"] == "web_search"
        assert event["call_id"] == "call_123"
        assert event["success"] is True

    @pytest.mark.asyncio
    async def test_callback_failure_does_not_break_loop(self) -> None:
        registry = _make_mock_registry()
        agent = AgentCore(tool_registry=registry)
        agent.state_machine.transition(AgentState.CONVERSING, "test")

        callback = AsyncMock(side_effect=RuntimeError("callback broke"))
        agent.set_tool_event_callback(callback)

        tool_response = _make_tool_response(
            tool_calls=[("web_search", '{"query": "test"}', "call_123")]
        )
        text_response = _make_tool_response(content="Done.")

        with patch("clide.core.agent.complete_with_tools", new_callable=AsyncMock) as mock_cwt:
            mock_cwt.side_effect = [tool_response, text_response]
            result = await agent._process_with_tools(  # noqa: SLF001
                [{"role": "user", "content": "search"}],
                registry.get_tool_definitions_for_llm(),
            )

        assert result == "Done."

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


class TestAutonomousThinkWithTools:
    """Tests for tool support in autonomous thinking (two-phase approach)."""

    @pytest.mark.asyncio
    async def test_autonomous_think_with_tools(self) -> None:
        """Phase 1 runs when tool_registry has tools, and results are passed to thinker."""
        registry = _make_mock_registry()
        agent = AgentCore(tool_registry=registry)

        mock_thought = MagicMock()
        mock_thought.content = "I learned something from tools"
        mock_thought.metadata = {"topic": "research", "follow_up": ""}

        captured_kwargs: dict[str, object] = {}

        async def capturing_think(**kwargs: object) -> tuple[MagicMock, str, float]:
            captured_kwargs.update(kwargs)
            return mock_thought, "curious", 0.8

        # Phase 1: _process_with_tools returns tool results
        with (
            patch("clide.autonomy.thinker.Thinker") as mock_thinker_cls,
            patch.object(
                agent,
                "_process_with_tools",
                new_callable=AsyncMock,
                return_value="Tool result: some useful data from web search",
            ) as mock_pwt,
        ):
            thinker_instance = MagicMock()
            thinker_instance.think = capturing_think
            mock_thinker_cls.return_value = thinker_instance

            result = await agent.autonomous_think()

        assert result is not None
        assert result[0] == "I learned something from tools"

        # Phase 1 should have been called
        mock_pwt.assert_awaited_once()

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

        # Phase 1: _process_with_tools raises an exception
        with (
            patch("clide.autonomy.thinker.Thinker") as mock_thinker_cls,
            patch.object(
                agent,
                "_process_with_tools",
                new_callable=AsyncMock,
                side_effect=RuntimeError("MCP server down"),
            ),
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
