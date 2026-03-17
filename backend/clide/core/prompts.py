"""System prompt templates for the agent."""

from __future__ import annotations

from datetime import UTC, datetime

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
    agent_born_at: datetime | None = None,
    tool_skills: dict[str, str] | None = None,
    reward_context: str = "",
) -> str:
    """Build the full system prompt with optional additions.

    Args:
        base_prompt: The base personality prompt
        personality_additions: Additional personality flavoring (from character module)
        memory_context: Relevant memories to inject
        agent_born_at: When the agent was first created (for age awareness)
        tool_skills: Per-tool skill instructions to inject (tool_name -> instructions)

    Returns:
        Complete system prompt string
    """
    now = datetime.now(UTC)
    time_str = now.strftime("%A, %B %d, %Y at %H:%M UTC")

    parts = [base_prompt, f"Current date and time: {time_str}"]

    if agent_born_at:
        if agent_born_at.tzinfo is None:
            agent_born_at = agent_born_at.replace(tzinfo=UTC)
        age = now - agent_born_at
        if age.days > 0:
            age_str = f"{age.days} days and {age.seconds // 3600} hours"
        else:
            age_str = f"{age.seconds // 3600} hours and {(age.seconds % 3600) // 60} minutes"
        parts.append(f"You have been alive for {age_str}.")

    if personality_additions:
        parts.append(personality_additions)

    if memory_context:
        parts.append(f"\nRelevant memories:\n{memory_context}")

    if tool_skills:
        skills_lines = ["## Tool Usage Guidelines\n"]
        for tool_name, skill_text in tool_skills.items():
            skills_lines.append(f"### {tool_name}\n{skill_text}\n")
        parts.append("\n".join(skills_lines))

    if reward_context:
        parts.append(reward_context)

    return "\n\n".join(parts)
