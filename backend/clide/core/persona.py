"""Persona drift mitigation — summary extraction and reinforcement messages."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

import litellm

from clide.config.settings import PersonaSettings
from clide.core.llm import LLMConfig, _build_model_name

logger = logging.getLogger(__name__)

PERSONA_EXTRACTION_PROMPT = """\
Read the following character description and distill it into a 2-3 sentence \
persona essence. Focus on: core personality traits, speech patterns (specific \
verbal tics, vocabulary), emotional baseline, and key behavioral rules.

This summary will be used as a mid-conversation reminder to maintain character \
consistency. Write ONLY the 2-3 sentence summary. No preamble, no explanation.

Character description:
{system_prompt}"""

HISTORY_SUMMARIZE_PROMPT = """\
Summarize the following conversation from {agent_name}'s perspective, \
as {agent_name} would remember it. Capture key facts, emotional beats, \
and any commitments made. Keep it under 200 words. Write in first person \
as {agent_name}.

Conversation:
{messages_text}"""


class PersonaManager:
    """Manages persona summary extraction and mid-conversation reinforcement."""

    def __init__(
        self,
        llm_config: LLMConfig,
        persona_settings: PersonaSettings | None = None,
    ) -> None:
        self.llm_config = llm_config
        self.settings = persona_settings or PersonaSettings()
        self._cached_summary: str = ""
        self._source_prompt_hash: str = ""

    async def get_summary(self, system_prompt: str) -> str:
        """Get or generate persona summary from system prompt."""
        if self.settings.persona_summary:
            return self.settings.persona_summary

        prompt_hash = hashlib.md5(system_prompt.encode()).hexdigest()  # noqa: S324
        if self._cached_summary and self._source_prompt_hash == prompt_hash:
            return self._cached_summary

        self._cached_summary = await self._extract_summary(system_prompt)
        self._source_prompt_hash = prompt_hash
        logger.info("Persona summary generated: %s", self._cached_summary[:100])
        return self._cached_summary

    async def _extract_summary(self, system_prompt: str) -> str:
        """Extract a compressed persona essence via LLM."""
        try:
            model_name = _build_model_name(self.llm_config)
            prompt = PERSONA_EXTRACTION_PROMPT.format(system_prompt=system_prompt)

            kwargs: dict[str, Any] = {
                "model": model_name,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 150,
                "stream": False,
            }
            if self.llm_config.api_base:
                kwargs["api_base"] = self.llm_config.api_base

            response = await litellm.acompletion(**kwargs)
            return str(response.choices[0].message.content or "").strip()
        except Exception:
            logger.warning("Failed to extract persona summary", exc_info=True)
            return ""

    async def summarize_history(self, messages: list[dict[str, Any]], agent_name: str) -> str:
        """Summarize conversation messages from the agent's perspective."""
        try:
            messages_text = "\n".join(
                f"{m.get('role', 'unknown')}: {m.get('content', '')[:200]}"
                for m in messages
                if m.get("role") in ("user", "assistant")
            )
            prompt = HISTORY_SUMMARIZE_PROMPT.format(
                agent_name=agent_name, messages_text=messages_text
            )

            model_name = _build_model_name(self.llm_config)
            kwargs: dict[str, Any] = {
                "model": model_name,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 300,
                "stream": False,
            }
            if self.llm_config.api_base:
                kwargs["api_base"] = self.llm_config.api_base

            response = await litellm.acompletion(**kwargs)
            return str(response.choices[0].message.content or "").strip()
        except Exception:
            logger.warning("Failed to summarize conversation history", exc_info=True)
            return ""

    @staticmethod
    def build_reinforcement_message(summary: str) -> dict[str, str]:
        """Build a system-role persona reminder message."""
        return {
            "role": "system",
            "content": (
                f"[PERSONA REMINDER] Stay in character. {summary} "
                "Do not break character. Do not use generic assistant language."
            ),
        }
