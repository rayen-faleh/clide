"""Tests for application settings."""

from __future__ import annotations

from pathlib import Path

from clide.config.settings import Settings


class TestSettingsFromYaml:
    def test_settings_from_yaml_loads_correctly(self, tmp_path: Path) -> None:
        yaml_content = """\
agent:
  name: "TestAgent"
  llm:
    provider: "openai"
    model: "gpt-4"
    max_tokens: 2048
  states:
    sleep_schedule:
      enabled: true
      start: "02:00"
      end: "08:00"
    thinking:
      interval_seconds: 600
      max_tokens_per_cycle: 3000
      max_consecutive_cycles: 3
    working:
      max_tool_steps: 5
    conversing:
      idle_timeout_seconds: 120
    budget:
      daily_token_limit: 100000
      warning_threshold: 0.9
  character:
    base_traits:
      curiosity: 0.5
      warmth: 0.6
      humor: 0.3
      assertiveness: 0.2
      creativity: 0.9
"""
        yaml_file = tmp_path / "agent.yaml"
        yaml_file.write_text(yaml_content)

        settings = Settings.from_yaml(yaml_file)

        assert settings.agent.name == "TestAgent"
        assert settings.agent.llm.provider == "openai"
        assert settings.agent.llm.model == "gpt-4"
        assert settings.agent.llm.max_tokens == 2048
        assert settings.agent.states.sleep_schedule.enabled is True
        assert settings.agent.states.sleep_schedule.start == "02:00"
        assert settings.agent.states.thinking.interval_seconds == 600
        assert settings.agent.states.working.max_tool_steps == 5
        assert settings.agent.states.conversing.idle_timeout_seconds == 120
        assert settings.agent.states.budget.daily_token_limit == 100000
        assert settings.agent.states.budget.warning_threshold == 0.9
        assert settings.agent.character.base_traits.curiosity == 0.5
        assert settings.agent.character.base_traits.creativity == 0.9

    def test_settings_defaults_when_no_file(self) -> None:
        settings = Settings.from_yaml("/nonexistent/path/agent.yaml")

        assert settings.agent.name == "Clide"
        assert settings.agent.llm.provider == "anthropic"
        assert settings.agent.llm.model == "claude-sonnet-4-20250514"
        assert settings.agent.llm.max_tokens == 4096
        assert settings.agent.states.sleep_schedule.enabled is False
        assert settings.agent.states.thinking.interval_seconds == 300
        assert settings.agent.states.budget.daily_token_limit == 500000
        assert settings.agent.character.base_traits.curiosity == 0.8

    def test_settings_partial_yaml(self, tmp_path: Path) -> None:
        yaml_content = """\
agent:
  name: "PartialAgent"
  llm:
    model: "custom-model"
"""
        yaml_file = tmp_path / "agent.yaml"
        yaml_file.write_text(yaml_content)

        settings = Settings.from_yaml(yaml_file)

        assert settings.agent.name == "PartialAgent"
        assert settings.agent.llm.model == "custom-model"
        # Defaults should fill in the rest
        assert settings.agent.llm.provider == "anthropic"
        assert settings.agent.llm.max_tokens == 4096
        assert settings.agent.states.sleep_schedule.enabled is False
        assert settings.agent.character.base_traits.curiosity == 0.8
