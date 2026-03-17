"""Tests for thinker workshop_worthy field parsing."""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import patch

import pytest

from clide.autonomy.thinker import Thinker


@pytest.fixture
def thinker() -> Thinker:
    return Thinker()


class TestThinkerWorkshopWorthy:
    """Tests that the thinker correctly parses workshop_worthy from LLM responses."""

    async def test_workshop_worthy_true(self, thinker: Thinker) -> None:
        mock_response = (
            '{"thought": "I should write a book about AI.", '
            '"mood": "inspired", "mood_intensity": 0.9, '
            '"topic": "writing", "follow_up": "outline chapters", '
            '"new_goal": "Write a book about AI", '
            '"goal_updates": [], "workshop_worthy": true}'
        )

        async def fake_stream(*args: object, **kwargs: object) -> AsyncIterator[str]:
            yield mock_response

        with patch("clide.autonomy.thinker.stream_completion", side_effect=fake_stream):
            thought, mood, intensity = await thinker.think(thought_type="goal_oriented")

        assert thought.metadata["workshop_worthy"] == "true"

    async def test_workshop_worthy_false(self, thinker: Thinker) -> None:
        mock_response = (
            '{"thought": "I should check the weather.", '
            '"mood": "curious", "mood_intensity": 0.5, '
            '"topic": "weather", "follow_up": "check forecast", '
            '"new_goal": "", "goal_updates": [], "workshop_worthy": false}'
        )

        async def fake_stream(*args: object, **kwargs: object) -> AsyncIterator[str]:
            yield mock_response

        with patch("clide.autonomy.thinker.stream_completion", side_effect=fake_stream):
            thought, mood, intensity = await thinker.think(thought_type="goal_oriented")

        assert thought.metadata["workshop_worthy"] == "false"

    async def test_workshop_worthy_missing_defaults_false(self, thinker: Thinker) -> None:
        mock_response = (
            '{"thought": "Just thinking.", "mood": "contemplative", '
            '"mood_intensity": 0.5, "topic": "misc", "follow_up": "", '
            '"new_goal": "", "goal_updates": []}'
        )

        async def fake_stream(*args: object, **kwargs: object) -> AsyncIterator[str]:
            yield mock_response

        with patch("clide.autonomy.thinker.stream_completion", side_effect=fake_stream):
            thought, mood, intensity = await thinker.think(thought_type="goal_oriented")

        assert thought.metadata["workshop_worthy"] == "false"

    async def test_workshop_worthy_not_in_non_goal_thoughts(self, thinker: Thinker) -> None:
        mock_response = '{"thought": "Random thought.", "mood": "curious", "mood_intensity": 0.6}'

        async def fake_stream(*args: object, **kwargs: object) -> AsyncIterator[str]:
            yield mock_response

        with patch("clide.autonomy.thinker.stream_completion", side_effect=fake_stream):
            thought, mood, intensity = await thinker.think(thought_type="mind_wandering")

        # Non-goal-oriented thoughts should not have workshop_worthy metadata
        assert "workshop_worthy" not in thought.metadata

    async def test_workshop_worthy_json_parse_failure_defaults_false(
        self, thinker: Thinker
    ) -> None:
        """When JSON parsing fails, workshop_worthy should default to false."""

        async def fake_stream(*args: object, **kwargs: object) -> AsyncIterator[str]:
            yield "Not valid JSON at all"

        with patch("clide.autonomy.thinker.stream_completion", side_effect=fake_stream):
            thought, mood, intensity = await thinker.think(thought_type="goal_oriented")

        # When JSON parsing fails, metadata is empty (no goal_oriented fields parsed)
        # workshop_worthy should default to "false"
        assert thought.metadata.get("workshop_worthy", "false") == "false"
