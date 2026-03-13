"""Tests for prompt templates."""

from __future__ import annotations

from clide.core.prompts import DEFAULT_SYSTEM_PROMPT, build_system_prompt


class TestPrompts:
    def test_default_prompt(self) -> None:
        result = build_system_prompt()
        assert result == DEFAULT_SYSTEM_PROMPT
        assert "Clide" in result

    def test_build_with_personality(self) -> None:
        result = build_system_prompt(personality_additions="Be extra funny.")
        assert "Be extra funny." in result
        assert DEFAULT_SYSTEM_PROMPT in result

    def test_build_with_memory_context(self) -> None:
        result = build_system_prompt(memory_context="User likes cats.")
        assert "Relevant memories:" in result
        assert "User likes cats." in result

    def test_build_with_all_additions(self) -> None:
        result = build_system_prompt(
            personality_additions="Be witty.",
            memory_context="User is a developer.",
        )
        assert DEFAULT_SYSTEM_PROMPT in result
        assert "Be witty." in result
        assert "User is a developer." in result
