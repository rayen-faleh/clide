"""System prompt templates for the agent."""

from __future__ import annotations

DEFAULT_SYSTEM_PROMPT = (
    "You are Clide, a curious and thoughtful AI agent. "
    "You are always eager to learn and explore new ideas. "
    "You have a warm personality and enjoy meaningful conversations. "
    "Respond naturally and thoughtfully."
)


def build_system_prompt(
    base_prompt: str = DEFAULT_SYSTEM_PROMPT,
    personality_additions: str = "",
    memory_context: str = "",
) -> str:
    """Build the full system prompt with optional additions.

    Args:
        base_prompt: The base personality prompt
        personality_additions: Additional personality flavoring (from character module)
        memory_context: Relevant memories to inject

    Returns:
        Complete system prompt string
    """
    parts = [base_prompt]

    if personality_additions:
        parts.append(personality_additions)

    if memory_context:
        parts.append(f"\n\nRelevant memories:\n{memory_context}")

    return "\n\n".join(parts)
