"""Tests for personality traits module."""

from __future__ import annotations

from clide.character.traits import PersonalityTraits


class TestPersonalityTraitsDefaults:
    def test_default_traits(self) -> None:
        traits = PersonalityTraits()
        assert traits.curiosity == 0.8
        assert traits.warmth == 0.7
        assert traits.humor == 0.5
        assert traits.assertiveness == 0.4
        assert traits.creativity == 0.7


class TestPersonalityTraitsSerialization:
    def test_traits_from_dict(self) -> None:
        data = {
            "curiosity": 0.9,
            "warmth": 0.3,
            "humor": 0.6,
            "assertiveness": 0.1,
            "creativity": 0.5,
        }
        traits = PersonalityTraits.from_dict(data)
        assert traits.curiosity == 0.9
        assert traits.warmth == 0.3
        assert traits.humor == 0.6
        assert traits.assertiveness == 0.1
        assert traits.creativity == 0.5

    def test_traits_to_dict_round_trip(self) -> None:
        original = PersonalityTraits(
            curiosity=0.9, warmth=0.3, humor=0.6, assertiveness=0.1, creativity=0.5
        )
        data = original.to_dict()
        restored = PersonalityTraits.from_dict(data)
        assert restored.to_dict() == original.to_dict()


class TestPersonalityTraitsClamp:
    def test_clamp_keeps_in_bounds(self) -> None:
        traits = PersonalityTraits(
            curiosity=1.5, warmth=-0.3, humor=0.5, assertiveness=2.0, creativity=-1.0
        )
        traits.clamp()
        assert traits.curiosity == 1.0
        assert traits.warmth == 0.0
        assert traits.humor == 0.5
        assert traits.assertiveness == 1.0
        assert traits.creativity == 0.0


class TestPersonalityTraitsNudge:
    def test_nudge_positive(self) -> None:
        traits = PersonalityTraits(curiosity=0.5)
        traits.nudge("curiosity", 0.01)
        assert traits.curiosity == 0.51

    def test_nudge_negative(self) -> None:
        traits = PersonalityTraits(warmth=0.5)
        traits.nudge("warmth", -0.01)
        assert traits.warmth == 0.49

    def test_nudge_respects_max_delta(self) -> None:
        traits = PersonalityTraits(humor=0.5)
        traits.nudge("humor", 0.1, max_delta=0.02)
        assert traits.humor == 0.52

    def test_nudge_invalid_trait_ignored(self) -> None:
        traits = PersonalityTraits()
        original = traits.to_dict()
        traits.nudge("nonexistent", 0.1)
        assert traits.to_dict() == original


class TestPersonalityTraitsDescribe:
    def test_describe_high_curiosity(self) -> None:
        traits = PersonalityTraits(curiosity=0.9)
        desc = traits.describe()
        assert "deeply curious" in desc

    def test_describe_low_curiosity(self) -> None:
        traits = PersonalityTraits(curiosity=0.2)
        desc = traits.describe()
        assert "focused and practical" in desc

    def test_describe_contains_all_aspects(self) -> None:
        traits = PersonalityTraits()
        desc = traits.describe()
        # Should start with "You are"
        assert desc.startswith("You are ")
        # With default traits, should have descriptions for all 5 traits
        # curiosity=0.8 -> "deeply curious"
        assert "curious" in desc
        # warmth=0.7 -> "friendly but measured" (0.7 is not > 0.7)
        assert "friendly" in desc
        # humor=0.5 -> "occasionally humorous"
        assert "humorous" in desc or "humor" in desc
        # assertiveness=0.4 -> "balanced"
        assert "balanced" in desc or "accommodating" in desc
        # creativity=0.7 -> "highly creative"
        assert "creative" in desc
