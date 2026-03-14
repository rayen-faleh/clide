"""Tests for prompt templates."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from clide.core.prompts import DEFAULT_SYSTEM_PROMPT, build_system_prompt


class TestPrompts:
    def test_default_prompt_contains_current_time(self) -> None:
        result = build_system_prompt()
        assert "Clide" in result
        assert "Current date and time:" in result

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

    def test_build_with_born_at_shows_age(self) -> None:
        born = datetime.now(UTC) - timedelta(days=3, hours=2)
        result = build_system_prompt(agent_born_at=born)
        assert "You have been alive for 3 days and 2 hours." in result

    def test_build_with_born_at_hours_only(self) -> None:
        born = datetime.now(UTC) - timedelta(hours=5, minutes=30)
        result = build_system_prompt(agent_born_at=born)
        assert "You have been alive for 5 hours and 30 minutes." in result

    def test_build_with_naive_born_at(self) -> None:
        born = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)
        result = build_system_prompt(agent_born_at=born)
        assert "You have been alive for" in result

    def test_build_without_born_at_has_no_age(self) -> None:
        result = build_system_prompt()
        assert "You have been alive" not in result
