"""Tests for the autonomous thinker."""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import patch

import pytest

from clide.autonomy.thinker import THINKING_PROMPT, Thinker


@pytest.fixture
def thinker() -> Thinker:
    return Thinker()


class TestThinker:
    async def test_think_returns_thought_and_mood(self, thinker: Thinker) -> None:
        mock_response = (
            '{"thought": "I wonder about the stars.", "mood": "curious", '
            '"mood_intensity": 0.8, "topic": "astronomy", "follow_up": "research constellations"}'
        )

        async def fake_stream(*args: object, **kwargs: object) -> AsyncIterator[str]:
            yield mock_response

        with patch("clide.autonomy.thinker.stream_completion", side_effect=fake_stream):
            thought, mood, intensity = await thinker.think()

        assert thought.content == "I wonder about the stars."
        assert thought.source == "autonomous"
        assert mood == "curious"
        assert intensity == 0.8
        assert thought.metadata["topic"] == "astronomy"
        assert thought.metadata["follow_up"] == "research constellations"

    async def test_think_with_invalid_json_fallback(self, thinker: Thinker) -> None:
        async def fake_stream(*args: object, **kwargs: object) -> AsyncIterator[str]:
            yield "Just a plain text thought"

        with patch("clide.autonomy.thinker.stream_completion", side_effect=fake_stream):
            thought, mood, intensity = await thinker.think()

        assert thought.content == "Just a plain text thought"
        assert mood == "contemplative"
        assert intensity == 0.5

    async def test_think_includes_memory_context(self, thinker: Thinker) -> None:
        mock_response = (
            '{"thought": "Connecting memories.", "mood": "inspired", '
            '"mood_intensity": 0.7, "topic": "connections", "follow_up": ""}'
        )
        captured_messages: list[object] = []

        async def fake_stream(
            messages: object, *args: object, **kwargs: object
        ) -> AsyncIterator[str]:
            captured_messages.append(messages)
            yield mock_response

        with patch("clide.autonomy.thinker.stream_completion", side_effect=fake_stream):
            thought, mood, intensity = await thinker.think(
                memory_context="User talked about space.",
                mood_context="curious",
            )

        assert thought.content == "Connecting memories."
        assert mood == "inspired"
        assert intensity == 0.7
        # Verify context was included in prompt
        prompt = captured_messages[0][0]["content"]  # type: ignore[index]
        assert "User talked about space." in prompt
        assert "curious" in prompt

    async def test_think_includes_personality_context(self, thinker: Thinker) -> None:
        mock_response = '{"thought": "Deep.", "mood": "contemplative", "mood_intensity": 0.5}'
        captured_messages: list[object] = []

        async def fake_stream(
            messages: object, *args: object, **kwargs: object
        ) -> AsyncIterator[str]:
            captured_messages.append(messages)
            yield mock_response

        with patch("clide.autonomy.thinker.stream_completion", side_effect=fake_stream):
            await thinker.think(personality_context="You are deeply curious and creative.")

        prompt = captured_messages[0][0]["content"]  # type: ignore[index]
        assert "You are deeply curious and creative." in prompt

    async def test_think_includes_opinions_context(self, thinker: Thinker) -> None:
        mock_response = '{"thought": "Hmm.", "mood": "focused", "mood_intensity": 0.6}'
        captured_messages: list[object] = []

        async def fake_stream(
            messages: object, *args: object, **kwargs: object
        ) -> AsyncIterator[str]:
            captured_messages.append(messages)
            yield mock_response

        with patch("clide.autonomy.thinker.stream_completion", side_effect=fake_stream):
            await thinker.think(opinions_context="- On AI: cautiously optimistic (confidence: 0.8)")

        prompt = captured_messages[0][0]["content"]  # type: ignore[index]
        assert "cautiously optimistic" in prompt

    async def test_think_includes_goals_context(self, thinker: Thinker) -> None:
        mock_response = '{"thought": "Goals.", "mood": "focused", "mood_intensity": 0.7}'
        captured_messages: list[object] = []

        async def fake_stream(
            messages: object, *args: object, **kwargs: object
        ) -> AsyncIterator[str]:
            captured_messages.append(messages)
            yield mock_response

        with patch("clide.autonomy.thinker.stream_completion", side_effect=fake_stream):
            await thinker.think(goals_context="- Learn about astronomy (progress: 30%)")

        prompt = captured_messages[0][0]["content"]  # type: ignore[index]
        assert "Learn about astronomy" in prompt

    async def test_think_includes_thought_history(self, thinker: Thinker) -> None:
        mock_response = '{"thought": "Building.", "mood": "inspired", "mood_intensity": 0.8}'
        captured_messages: list[object] = []

        async def fake_stream(
            messages: object, *args: object, **kwargs: object
        ) -> AsyncIterator[str]:
            captured_messages.append(messages)
            yield mock_response

        with patch("clide.autonomy.thinker.stream_completion", side_effect=fake_stream):
            await thinker.think(thought_history="- I was thinking about fractals earlier")

        prompt = captured_messages[0][0]["content"]  # type: ignore[index]
        assert "fractals" in prompt

    async def test_think_clamps_intensity(self, thinker: Thinker) -> None:
        mock_response = '{"thought": "Test", "mood": "excited", "mood_intensity": 1.5}'

        async def fake_stream(*args: object, **kwargs: object) -> AsyncIterator[str]:
            yield mock_response

        with patch("clide.autonomy.thinker.stream_completion", side_effect=fake_stream):
            _, _, intensity = await thinker.think()

        assert intensity == 1.0

    async def test_think_empty_response_fallback(self, thinker: Thinker) -> None:
        async def fake_stream(*args: object, **kwargs: object) -> AsyncIterator[str]:
            yield ""

        with patch("clide.autonomy.thinker.stream_completion", side_effect=fake_stream):
            thought, mood, intensity = await thinker.think()

        assert thought.content == "Reflecting quietly..."
        assert mood == "contemplative"

    async def test_think_parses_json_in_markdown_code_block(self, thinker: Thinker) -> None:
        """Test that _extract_json handles markdown-wrapped JSON from small models."""
        mock_response = (
            '```json\n{"thought": "Wrapped thought.", "mood": "amused", '
            '"mood_intensity": 0.6, "topic": "humor", "follow_up": ""}\n```'
        )

        async def fake_stream(*args: object, **kwargs: object) -> AsyncIterator[str]:
            yield mock_response

        with patch("clide.autonomy.thinker.stream_completion", side_effect=fake_stream):
            thought, mood, intensity = await thinker.think()

        assert thought.content == "Wrapped thought."
        assert mood == "amused"
        assert intensity == 0.6

    async def test_think_with_all_context_empty(self, thinker: Thinker) -> None:
        mock_response = '{"thought": "Starting fresh.", "mood": "neutral", "mood_intensity": 0.3}'

        async def fake_stream(*args: object, **kwargs: object) -> AsyncIterator[str]:
            yield mock_response

        with patch("clide.autonomy.thinker.stream_completion", side_effect=fake_stream):
            thought, mood, intensity = await thinker.think()

        assert thought.content == "Starting fresh."
        assert mood == "neutral"
        assert intensity == 0.3

    async def test_think_includes_all_valid_moods_in_prompt(self, thinker: Thinker) -> None:
        mock_response = '{"thought": "Test.", "mood": "neutral", "mood_intensity": 0.5}'
        captured_messages: list[object] = []

        async def fake_stream(
            messages: object, *args: object, **kwargs: object
        ) -> AsyncIterator[str]:
            captured_messages.append(messages)
            yield mock_response

        with patch("clide.autonomy.thinker.stream_completion", side_effect=fake_stream):
            await thinker.think()

        prompt = captured_messages[0][0]["content"]  # type: ignore[index]
        for mood_name in [
            "curious",
            "excited",
            "contemplative",
            "playful",
            "focused",
            "content",
            "melancholy",
            "frustrated",
            "amused",
            "inspired",
            "tired",
            "neutral",
        ]:
            assert mood_name in prompt, f"Mood '{mood_name}' not found in prompt"

    async def test_anti_repetition_instruction_in_prompt(self) -> None:
        assert "Do NOT repeat" in THINKING_PROMPT
        assert "PREVIOUS thoughts" in THINKING_PROMPT

    async def test_think_with_max_goals_in_prompt(self, thinker: Thinker) -> None:
        mock_response = '{"thought": "Goals.", "mood": "focused", "mood_intensity": 0.7}'
        captured_messages: list[object] = []

        async def fake_stream(
            messages: object, *args: object, **kwargs: object
        ) -> AsyncIterator[str]:
            captured_messages.append(messages)
            yield mock_response

        with patch("clide.autonomy.thinker.stream_completion", side_effect=fake_stream):
            await thinker.think(max_goals=3)

        prompt = captured_messages[0][0]["content"]  # type: ignore[index]
        assert "3" in prompt
        assert "active goals" in prompt

    async def test_think_extracts_new_goal(self, thinker: Thinker) -> None:
        mock_response = (
            '{"thought": "I want to learn.", "mood": "curious", '
            '"mood_intensity": 0.8, "topic": "learning", "follow_up": "", '
            '"new_goal": "Study quantum physics"}'
        )

        async def fake_stream(*args: object, **kwargs: object) -> AsyncIterator[str]:
            yield mock_response

        with patch("clide.autonomy.thinker.stream_completion", side_effect=fake_stream):
            thought, _, _ = await thinker.think()

        assert thought.metadata["new_goal"] == "Study quantum physics"

    async def test_think_extracts_goal_updates(self, thinker: Thinker) -> None:
        import json

        mock_response = json.dumps(
            {
                "thought": "Making progress.",
                "mood": "focused",
                "mood_intensity": 0.7,
                "topic": "progress",
                "follow_up": "",
                "new_goal": "",
                "goal_updates": [
                    {
                        "description": "astronomy",
                        "progress": 0.5,
                        "status": "active",
                        "reason": "read a chapter",
                    }
                ],
            }
        )

        async def fake_stream(*args: object, **kwargs: object) -> AsyncIterator[str]:
            yield mock_response

        with patch("clide.autonomy.thinker.stream_completion", side_effect=fake_stream):
            thought, _, _ = await thinker.think()

        updates = json.loads(thought.metadata["goal_updates"])
        assert len(updates) == 1
        assert updates[0]["description"] == "astronomy"
        assert updates[0]["progress"] == 0.5

    async def test_think_with_tool_results(self, thinker: Thinker) -> None:
        mock_response = '{"thought": "Tools helped.", "mood": "focused", "mood_intensity": 0.7}'
        captured_messages: list[object] = []

        async def fake_stream(
            messages: object, *args: object, **kwargs: object
        ) -> AsyncIterator[str]:
            captured_messages.append(messages)
            yield mock_response

        with patch("clide.autonomy.thinker.stream_completion", side_effect=fake_stream):
            await thinker.think(tool_results_context="Search returned 5 results about AI.")

        prompt = captured_messages[0][0]["content"]  # type: ignore[index]
        assert "Search returned 5 results about AI." in prompt
        assert "Incorporate these results into your thinking." in prompt

    async def test_think_without_tool_results(self, thinker: Thinker) -> None:
        mock_response = '{"thought": "No tools.", "mood": "neutral", "mood_intensity": 0.4}'
        captured_messages: list[object] = []

        async def fake_stream(
            messages: object, *args: object, **kwargs: object
        ) -> AsyncIterator[str]:
            captured_messages.append(messages)
            yield mock_response

        with patch("clide.autonomy.thinker.stream_completion", side_effect=fake_stream):
            await thinker.think(tool_results_context="")

        prompt = captured_messages[0][0]["content"]  # type: ignore[index]
        assert "Tool results from your exploration" not in prompt
        assert "Incorporate these results" not in prompt

    async def test_think_tool_results_in_metadata(self, thinker: Thinker) -> None:
        mock_response = '{"thought": "Using tools.", "mood": "focused", "mood_intensity": 0.6}'

        async def fake_stream(*args: object, **kwargs: object) -> AsyncIterator[str]:
            yield mock_response

        with patch("clide.autonomy.thinker.stream_completion", side_effect=fake_stream):
            thought, _, _ = await thinker.think(tool_results_context="Weather API returned sunny.")

        assert thought.metadata["used_tools"] == "true"

        # Also verify it's NOT set when no tool results
        with patch("clide.autonomy.thinker.stream_completion", side_effect=fake_stream):
            thought_no_tools, _, _ = await thinker.think(tool_results_context="")

        assert "used_tools" not in thought_no_tools.metadata

    async def test_think_no_goals_in_response(self, thinker: Thinker) -> None:
        mock_response = '{"thought": "Just thinking.", "mood": "neutral", "mood_intensity": 0.4}'

        async def fake_stream(*args: object, **kwargs: object) -> AsyncIterator[str]:
            yield mock_response

        with patch("clide.autonomy.thinker.stream_completion", side_effect=fake_stream):
            thought, _, _ = await thinker.think()

        assert thought.metadata["new_goal"] == ""
        assert thought.metadata["goal_updates"] == "[]"

    async def test_think_with_mind_wandering_type(self, thinker: Thinker) -> None:
        mock_response = '{"thought": "Random musing.", "mood": "playful", "mood_intensity": 0.4}'
        captured_messages: list[object] = []

        async def fake_stream(
            messages: object, *args: object, **kwargs: object
        ) -> AsyncIterator[str]:
            captured_messages.append(messages)
            yield mock_response

        with patch("clide.autonomy.thinker.stream_completion", side_effect=fake_stream):
            thought, mood, intensity = await thinker.think(thought_type="mind_wandering")

        prompt = captured_messages[0][0]["content"]  # type: ignore[index]
        assert "wandering" in prompt.lower()
        assert thought.content == "Random musing."

    async def test_think_with_self_reflection_type(self, thinker: Thinker) -> None:
        mock_response = (
            '{"thought": "Looking inward.", "mood": "contemplative", "mood_intensity": 0.6}'
        )
        captured_messages: list[object] = []

        async def fake_stream(
            messages: object, *args: object, **kwargs: object
        ) -> AsyncIterator[str]:
            captured_messages.append(messages)
            yield mock_response

        with patch("clide.autonomy.thinker.stream_completion", side_effect=fake_stream):
            thought, mood, intensity = await thinker.think(thought_type="self_reflection")

        prompt = captured_messages[0][0]["content"]  # type: ignore[index]
        assert "reflect" in prompt.lower() or "self" in prompt.lower()

    async def test_think_with_goal_oriented_type(self, thinker: Thinker) -> None:
        mock_response = (
            '{"thought": "Working on goals.", "mood": "focused", "mood_intensity": 0.8, '
            '"topic": "goals", "follow_up": "next step", "new_goal": "", "goal_updates": []}'
        )
        captured_messages: list[object] = []

        async def fake_stream(
            messages: object, *args: object, **kwargs: object
        ) -> AsyncIterator[str]:
            captured_messages.append(messages)
            yield mock_response

        with patch("clide.autonomy.thinker.stream_completion", side_effect=fake_stream):
            thought, mood, intensity = await thinker.think(thought_type="goal_oriented")

        prompt = captured_messages[0][0]["content"]  # type: ignore[index]
        assert "follow_up" in prompt
        assert "new_goal" in prompt
        assert "goal_updates" in prompt

    async def test_think_minimal_json_for_non_goal(self, thinker: Thinker) -> None:
        """Non-goal types should work with minimal JSON (no topic/follow_up/goals)."""
        mock_response = '{"thought": "Just a thought.", "mood": "amused", "mood_intensity": 0.5}'

        async def fake_stream(*args: object, **kwargs: object) -> AsyncIterator[str]:
            yield mock_response

        with patch("clide.autonomy.thinker.stream_completion", side_effect=fake_stream):
            thought, mood, intensity = await thinker.think(thought_type="mind_wandering")

        assert thought.content == "Just a thought."
        assert mood == "amused"
        assert intensity == 0.5
        # Non-goal types should not have goal-related metadata
        assert "new_goal" not in thought.metadata
        assert "goal_updates" not in thought.metadata

    async def test_thought_type_set_on_returned_thought(self, thinker: Thinker) -> None:
        mock_response = '{"thought": "Observing.", "mood": "neutral", "mood_intensity": 0.3}'

        async def fake_stream(*args: object, **kwargs: object) -> AsyncIterator[str]:
            yield mock_response

        with patch("clide.autonomy.thinker.stream_completion", side_effect=fake_stream):
            thought, _, _ = await thinker.think(thought_type="observation")

        assert thought.thought_type == "observation"
