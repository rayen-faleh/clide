"""Application settings loaded from config/agent.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel


class LLMSettings(BaseModel):
    provider: str = "ollama"
    model: str = "llama3.2"
    max_tokens: int = 4096
    api_base: str = ""


class SleepScheduleSettings(BaseModel):
    enabled: bool = False
    start: str = "01:00"
    end: str = "07:00"


class ThinkingSettings(BaseModel):
    interval_seconds: int = 300
    max_tokens_per_cycle: int = 2000
    max_consecutive_cycles: int = 5


class WorkingSettings(BaseModel):
    max_tool_steps: int = 10
    phase_size: int = 10
    max_phases: int = 3


class ConversingSettings(BaseModel):
    idle_timeout_seconds: int = 300


class BudgetSettings(BaseModel):
    daily_token_limit: int = 500000
    warning_threshold: float = 0.8


class StatesSettings(BaseModel):
    sleep_schedule: SleepScheduleSettings = SleepScheduleSettings()
    thinking: ThinkingSettings = ThinkingSettings()
    working: WorkingSettings = WorkingSettings()
    conversing: ConversingSettings = ConversingSettings()
    budget: BudgetSettings = BudgetSettings()


class CharacterTraits(BaseModel):
    curiosity: float = 0.8
    warmth: float = 0.7
    humor: float = 0.5
    assertiveness: float = 0.4
    creativity: float = 0.7


class CharacterSettings(BaseModel):
    base_traits: CharacterTraits = CharacterTraits()


class AgentSettings(BaseModel):
    name: str = "Clide"
    system_prompt: str = ""  # Empty = use default from prompts.py
    llm: LLMSettings = LLMSettings()
    states: StatesSettings = StatesSettings()
    character: CharacterSettings = CharacterSettings()


# Project root: backend/clide/config/settings.py -> ../../.. -> project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_DEFAULT_CONFIG = _PROJECT_ROOT / "config" / "agent.yaml"


class Settings(BaseModel):
    agent: AgentSettings = AgentSettings()

    @classmethod
    def from_yaml(cls, path: Path | str | None = None) -> Settings:
        """Load settings from a YAML file."""
        resolved = Path(path) if path is not None else _DEFAULT_CONFIG
        if not resolved.exists():
            return cls()
        with open(resolved) as f:
            data: dict[str, Any] = yaml.safe_load(f) or {}
        return cls.model_validate(data)
