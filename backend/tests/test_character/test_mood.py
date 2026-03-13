"""Tests for mood system module."""

from __future__ import annotations

from clide.character.mood import MoodState


class TestMoodStateDefaults:
    def test_default_mood(self) -> None:
        mood = MoodState()
        assert mood.mood == "neutral"
        assert mood.intensity == 0.5
        assert mood.reason == ""

    def test_invalid_mood_defaults_to_neutral(self) -> None:
        mood = MoodState(mood="nonexistent")
        assert mood.mood == "neutral"

    def test_intensity_clamped(self) -> None:
        mood_high = MoodState(intensity=1.5)
        assert mood_high.intensity == 1.0
        mood_low = MoodState(intensity=-0.5)
        assert mood_low.intensity == 0.0


class TestMoodStateTransition:
    def test_transition_same_mood_blends_intensity(self) -> None:
        mood = MoodState(mood="curious", intensity=0.5)
        mood.transition("curious", 0.8, blend_factor=0.3)
        # 0.5 * 0.7 + 0.8 * 0.3 = 0.35 + 0.24 = 0.59
        assert abs(mood.intensity - 0.59) < 0.001
        assert mood.mood == "curious"

    def test_transition_different_mood_switches_when_stronger(self) -> None:
        mood = MoodState(mood="neutral", intensity=0.3)
        mood.transition("excited", 0.9, blend_factor=0.5)
        # blended_new = 0.9 * 0.5 = 0.45
        # blended_current = 0.3 * 0.5 = 0.15
        # blended_new >= blended_current => switch
        assert mood.mood == "excited"

    def test_transition_different_mood_stays_when_weaker(self) -> None:
        mood = MoodState(mood="focused", intensity=0.9)
        mood.transition("playful", 0.2, blend_factor=0.3)
        # blended_new = 0.2 * 0.3 = 0.06
        # blended_current = 0.9 * 0.7 = 0.63
        # blended_new < blended_current => stays
        assert mood.mood == "focused"

    def test_transition_invalid_mood_ignored(self) -> None:
        mood = MoodState(mood="neutral", intensity=0.5)
        mood.transition("invalid_mood", 0.8)
        assert mood.mood == "neutral"
        assert mood.intensity == 0.5


class TestMoodStateDescribe:
    def test_describe_low_intensity(self) -> None:
        mood = MoodState(mood="curious", intensity=0.2)
        desc = mood.describe()
        assert "slightly" in desc
        assert "curious" in desc

    def test_describe_high_intensity(self) -> None:
        mood = MoodState(mood="excited", intensity=0.8)
        desc = mood.describe()
        assert "very" in desc
        assert "excited" in desc


class TestMoodStateSerialization:
    def test_to_dict_from_dict_round_trip(self) -> None:
        original = MoodState(mood="contemplative", intensity=0.7, reason="deep conversation")
        data = original.to_dict()
        restored = MoodState.from_dict(data)
        assert restored.mood == original.mood
        assert restored.intensity == original.intensity
        assert restored.reason == original.reason
