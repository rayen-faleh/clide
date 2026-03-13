"""Tests for the autonomous thinker."""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import patch

import pytest

from clide.autonomy.thinker import Thinker


@pytest.fixture
def thinker() -> Thinker:
    return Thinker()


class TestThinker:
    async def test_think_returns_thought_and_mood(self, thinker: Thinker) -> None:
        mock_response = (
            '{"thought": "I wonder about the stars.", "mood": "curious", "mood_intensity": 0.8}'
        )

        async def fake_stream(*args: object, **kwargs: object) -> AsyncIterator[str]:
            yield mock_response

        with patch("clide.autonomy.thinker.stream_completion", side_effect=fake_stream):
            thought, mood, intensity = await thinker.think()

        assert thought.content == "I wonder about the stars."
        assert thought.source == "autonomous"
        assert mood == "curious"
        assert intensity == 0.8

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
            '{"thought": "Connecting memories.", "mood": "inspired", "mood_intensity": 0.7}'
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
