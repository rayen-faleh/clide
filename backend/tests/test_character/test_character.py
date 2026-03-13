"""Integration tests for the Character manager."""

from __future__ import annotations

from pathlib import Path

import pytest

from clide.character.character import Character
from clide.character.mood import MoodState
from clide.character.opinions import Opinion
from clide.character.traits import PersonalityTraits


class TestCharacterCreation:
    def test_character_default_creation(self) -> None:
        char = Character()
        assert isinstance(char.traits, PersonalityTraits)
        assert isinstance(char.mood, MoodState)
        assert char.mood.mood == "neutral"


class TestCharacterPrompt:
    def test_build_personality_prompt_includes_traits(self) -> None:
        char = Character(traits=PersonalityTraits(curiosity=0.9))
        prompt = char.build_personality_prompt()
        assert "curious" in prompt

    def test_build_personality_prompt_includes_mood(self) -> None:
        char = Character(mood=MoodState(mood="excited", intensity=0.8))
        prompt = char.build_personality_prompt()
        assert "excited" in prompt

    def test_build_personality_prompt_includes_opinions(self) -> None:
        char = Character()
        char.opinions.set(Opinion(topic="Python", stance="Great language"))
        prompt = char.build_personality_prompt()
        assert "Python" in prompt
        assert "Great language" in prompt


class TestCharacterPersistence:
    @pytest.mark.asyncio
    async def test_save_and_load_round_trip(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test_character.db"

        # Create and save
        char = Character(
            traits=PersonalityTraits(curiosity=0.9, warmth=0.3),
            mood=MoodState(mood="excited", intensity=0.7, reason="testing"),
            db_path=db_path,
        )
        char.opinions.set(Opinion(topic="TDD", stance="Essential practice", confidence=0.8))
        await char.save()

        # Load into new instance
        loaded = Character(db_path=db_path)
        await loaded.load()

        assert loaded.traits.curiosity == 0.9
        assert loaded.traits.warmth == 0.3
        assert loaded.mood.mood == "excited"
        assert loaded.mood.intensity == 0.7
        assert loaded.mood.reason == "testing"
        tdd_opinion = loaded.opinions.get("tdd")
        assert tdd_opinion is not None
        assert tdd_opinion.stance == "Essential practice"

    @pytest.mark.asyncio
    async def test_load_without_existing_data(self, tmp_path: Path) -> None:
        db_path = tmp_path / "empty_character.db"
        char = Character(db_path=db_path)
        await char.load()
        # Should still have defaults
        assert char.traits.curiosity == 0.8
        assert char.mood.mood == "neutral"
        assert len(char.opinions.all()) == 0
