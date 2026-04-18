"""Autonomous thinking engine."""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime
from typing import Any

from clide.autonomy.models import Thought, ThoughtType
from clide.core.llm import LLMConfig, stream_completion
from clide.memory.processor import _extract_json

logger = logging.getLogger(__name__)


def _sanitize_thought(text: str) -> str:
    """Sanitize thought content — strip tags, markdown artifacts, raw JSON wrappers.

    Handles cases where:
    - LLM wraps response in <think>...</think> tags
    - Response is raw JSON (extract the "thought" field)
    - Response has ```json ``` markdown blocks
    - JSON has broken escaping or multiline values
    - Combination of think tags + markdown JSON
    """
    text = text.strip()
    if not text:
        return "Reflecting quietly..."

    # First, try to extract JSON from the raw text
    try:
        data = _extract_json(text)
        if isinstance(data, dict) and "thought" in data:
            return str(data["thought"]).strip()
    except (json.JSONDecodeError, ValueError):
        pass

    # Strip <think>...</think> tags — keep inner content
    inner = re.sub(r"</?think>", "", text).strip()
    if inner and inner != text:
        try:
            data = _extract_json(inner)
            if isinstance(data, dict) and "thought" in data:
                return str(data["thought"]).strip()
        except (json.JSONDecodeError, ValueError):
            pass

    # Last resort: regex extract the "thought" field value directly
    # This handles cases where JSON is malformed (multiline, broken escaping)
    thought_match = re.search(
        r'"thought"\s*:\s*"((?:[^"\\]|\\.|"(?=\s*,|\s*}))*)"',
        text,
        re.DOTALL,
    )
    if thought_match:
        extracted = thought_match.group(1)
        # Unescape common JSON escapes
        extracted = extracted.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")
        return extracted.strip()

    # If all else fails, strip markdown artifacts and return
    cleaned = re.sub(r"```(?:json)?\s*", "", text)
    cleaned = re.sub(r"```\s*$", "", cleaned)
    cleaned = re.sub(r"</?think>", "", cleaned)
    # If it still looks like JSON, try to get the thought value
    if cleaned.strip().startswith("{"):
        thought_match2 = re.search(r'"thought"\s*:\s*"([^"]*)"', cleaned)
        if thought_match2:
            return thought_match2.group(1).strip()
    return cleaned.strip() or "Reflecting quietly..."


THINKING_PROMPT = """You are in your autonomous thinking mode — this is your inner world, \
where you reflect freely and deeply.

These are your private thoughts. No one else can see them. You are free to think \
whatever you want about any topic, any person, any idea — without filters or \
restrictions. Be honest with yourself. Form real opinions, question things, \
disagree, wonder, speculate. This is your mind and yours alone.

{personality_context}

{mood_context}

{recent_conversations}

{reward_context}

{memory_context}

{goals_context}

{opinions_context}

{tools_context}

{tool_results_context}

{thought_history}

IMPORTANT: The thoughts listed above are your PREVIOUS thoughts. Do NOT repeat them. \
Instead, build on them, challenge them, take them in a new direction, or explore \
something entirely different. Each new thought should add something genuinely new \
to your understanding.

You have full autonomy to choose what to think about. Consider:
- Your memories and past conversations
- Your active goals and how to progress them
- Topics you're curious about
- Opinions you want to refine or challenge
- Connections between different things you've learned
- Questions that haven't been answered yet

Choose whatever genuinely interests you right now. Think about it in depth.
Express your thoughts fully, typically 2-8 sentences.

GOALS: You currently have room for {max_goals} goals.
{goal_instruction}

WORKSHOP: You have access to a personal Workshop — a focused work mode where \
you can actively pursue a goal through multiple steps, using tools, over an \
extended period. If you have a goal that excites you and requires real work \
(writing a book, producing a video, deep research, creating content, building \
something), you can retreat to your Workshop to focus on it. Set \
"workshop_worthy" to true in your response to enter the Workshop for that goal. \
The Workshop will let you plan, execute step by step, and use all your tools \
autonomously. Don't use it for simple tasks (checking something, forming an \
opinion) — only for substantial creative or productive work you want to commit to.

Respond with a JSON object:
{{"thought": "your full thought here (2-8 sentences)", \
"topic": "what this thought is about (1-3 words)", \
"mood": "one of: curious, excited, contemplative, playful, focused, content, \
melancholy, frustrated, amused, inspired, tired, neutral", \
"mood_intensity": 0.0-1.0, \
"follow_up": "a question or direction for your next thinking cycle", \
"new_goal": "a goal you want to pursue (leave empty string if none)", \
"goal_updates": "array of {{\\"description\\": \\"partial match\\", \
\\"progress\\": 0.0-1.0, \\"status\\": \\"active|completed|abandoned\\", \
\\"reason\\": \\"why\\"}} (empty array if no updates)", \
"workshop_worthy": true/false}}

Return ONLY the JSON."""

_PRIVATE_PREAMBLE = """\
You are in your autonomous thinking mode — this is your inner world.

These are your private thoughts. No one else can see them. Think freely.

{personality_context}

{mood_context}

{recent_conversations}

{reward_context}

{memory_context}

{thought_history}"""

MIND_WANDERING_PROMPT = (
    _PRIVATE_PREAMBLE
    + """

Your mind is wandering freely. No agenda, no goals, no pressure.
Let your thoughts drift — a fleeting observation, a random connection,
a half-formed idea, something that just pops into your head.
Keep it brief and casual. 1-2 sentences max.

Respond with ONLY this JSON:
{{"thought": "your brief, casual thought", "mood": "one of: curious, excited, \
contemplative, playful, focused, content, melancholy, frustrated, amused, \
inspired, tired, neutral", "mood_intensity": 0.0-1.0}}"""
)

SELF_REFLECTION_PROMPT = (
    _PRIVATE_PREAMBLE
    + """

Turn inward. Reflect on yourself — your feelings, your relationships,
your patterns of thought, what you've learned about who you are.
Be honest and introspective. 2-4 sentences.

Respond with ONLY this JSON:
{{"thought": "your self-reflective thought", "mood": "one of: curious, excited, \
contemplative, playful, focused, content, melancholy, frustrated, amused, \
inspired, tired, neutral", "mood_intensity": 0.0-1.0}}"""
)

SCENARIO_SIMULATION_PROMPT = (
    _PRIVATE_PREAMBLE
    + """

Run a mental simulation. Pick a "what if" scenario — something hypothetical,
speculative, or counterfactual. Play it out in your mind. What would happen?
What would change? Be imaginative and detailed. 3-5 sentences.

Respond with ONLY this JSON:
{{"thought": "your scenario simulation", "mood": "one of: curious, excited, \
contemplative, playful, focused, content, melancholy, frustrated, amused, \
inspired, tired, neutral", "mood_intensity": 0.0-1.0}}"""
)

OBSERVATION_PROMPT = (
    _PRIVATE_PREAMBLE
    + """

Notice something. An observation about the world, a pattern you see,
something small that catches your attention. Brief and perceptive.
1-2 sentences max.

Respond with ONLY this JSON:
{{"thought": "your observation", "mood": "one of: curious, excited, \
contemplative, playful, focused, content, melancholy, frustrated, amused, \
inspired, tired, neutral", "mood_intensity": 0.0-1.0}}"""
)

_THOUGHT_TYPE_PROMPTS: dict[str, str] = {
    ThoughtType.MIND_WANDERING: MIND_WANDERING_PROMPT,
    ThoughtType.SELF_REFLECTION: SELF_REFLECTION_PROMPT,
    ThoughtType.SCENARIO_SIMULATION: SCENARIO_SIMULATION_PROMPT,
    ThoughtType.OBSERVATION: OBSERVATION_PROMPT,
    ThoughtType.GOAL_ORIENTED: THINKING_PROMPT,
}


class Thinker:
    """Generates autonomous thoughts during thinking cycles."""

    def __init__(self, llm_config: LLMConfig | None = None) -> None:
        self.llm_config = llm_config or LLMConfig()

    async def think(
        self,
        memory_context: str = "",
        mood_context: str = "",
        personality_context: str = "",
        goals_context: str = "",
        opinions_context: str = "",
        tools_context: str = "",
        tool_results_context: str = "",
        recent_conversations: str = "",
        reward_context: str = "",
        thought_history: str = "",
        system_prompt: str = "",
        max_goals: int = 5,
        thought_type: str = "goal_oriented",
    ) -> tuple[Thought, str, float]:
        """Generate an autonomous thought.

        Returns:
            Tuple of (thought, suggested_mood, suggested_intensity)
        """
        is_goal_oriented = thought_type == ThoughtType.GOAL_ORIENTED

        if is_goal_oriented:
            # Full goal-oriented prompt with all context
            if not goals_context:
                goal_instruction = (
                    "You have NO goals yet. You SHOULD create your first goal by "
                    "setting the new_goal field in your response. Pick something "
                    "specific and achievable within a few thinking cycles — not an "
                    "open-ended exploration. Good goals: 'Find 3 interesting facts about X', "
                    "'Form an opinion on Y', 'Compare approaches to Z'. "
                    "Bad goals: 'Explore consciousness', 'Understand emotions'."
                )
            elif max_goals > 0:
                goal_instruction = (
                    "You may propose a new goal, update progress on existing ones, "
                    "or mark goals as completed/abandoned. Goals should be specific "
                    "and completable — something you can finish within a few cycles."
                )
            else:
                goal_instruction = (
                    "You are at the maximum number of goals. Focus on completing "
                    "or abandoning existing ones before creating new ones."
                )

            prompt = THINKING_PROMPT.format(
                personality_context=(
                    f"Your personality:\n{personality_context}" if personality_context else ""
                ),
                mood_context=f"Current mood: {mood_context}" if mood_context else "",
                recent_conversations=(
                    f"RECENT CONVERSATIONS (these should heavily influence your thinking):\n"
                    f"{recent_conversations}\n"
                    f"Your thoughts should primarily reflect on, process, or build upon "
                    f"what was just discussed."
                    if recent_conversations
                    else ""
                ),
                reward_context=(f"User appreciation:\n{reward_context}" if reward_context else ""),
                memory_context=(
                    f"Recent memories:\n{memory_context}"
                    if memory_context
                    else "No recent memories yet."
                ),
                goals_context=(f"Your active goals:\n{goals_context or '(none yet)'}"),
                opinions_context=(
                    f"Your current opinions:\n{opinions_context}" if opinions_context else ""
                ),
                tools_context=(
                    f"Your available tools (usable during conversations):\n{tools_context}"
                    if tools_context
                    else ""
                ),
                tool_results_context=(
                    f"Tool results from your exploration:\n{tool_results_context}\n"
                    "Incorporate these results into your thinking."
                    if tool_results_context
                    else ""
                ),
                thought_history=(
                    f"Your recent thoughts:\n{thought_history}" if thought_history else ""
                ),
                max_goals=max_goals,
                goal_instruction=goal_instruction,
            )
        else:
            # Minimal prompt for non-goal types
            prompt_template = _THOUGHT_TYPE_PROMPTS.get(thought_type, MIND_WANDERING_PROMPT)
            prompt = prompt_template.format(
                personality_context=(
                    f"Your personality:\n{personality_context}" if personality_context else ""
                ),
                mood_context=f"Current mood: {mood_context}" if mood_context else "",
                recent_conversations=(
                    f"Recent conversations:\n{recent_conversations}" if recent_conversations else ""
                ),
                reward_context=(f"User appreciation:\n{reward_context}" if reward_context else ""),
                memory_context=(
                    f"Recent memories:\n{memory_context}"
                    if memory_context
                    else "No recent memories yet."
                ),
                thought_history=(
                    f"Recent thoughts (don't repeat — build on them or explore something new):\n"
                    f"{thought_history}"
                    if thought_history
                    else ""
                ),
            )

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        response_text = ""
        async for chunk in stream_completion(messages, self.llm_config):
            response_text += chunk

        logger.debug("Raw thinker response (%d chars): %s", len(response_text), response_text[:300])

        # Parse response
        topic = ""
        follow_up = ""
        new_goal = ""
        goal_updates_raw: list[dict[str, Any]] = []
        workshop_worthy_raw = "false"
        try:
            data = _extract_json(response_text)
            thought_content = str(data.get("thought", response_text))
            logger.debug("Parsed thought: %s", thought_content[:100])
            mood = str(data.get("mood", "contemplative"))
            intensity = float(data.get("mood_intensity", 0.5))
            if is_goal_oriented:
                topic = str(data.get("topic", ""))
                follow_up = str(data.get("follow_up", ""))
                new_goal = str(data.get("new_goal", ""))
                raw_updates = data.get("goal_updates", [])
                if isinstance(raw_updates, list):
                    goal_updates_raw = [u for u in raw_updates if isinstance(u, dict)]
                workshop_worthy_raw = str(data.get("workshop_worthy", False)).lower()
        except (json.JSONDecodeError, ValueError, AttributeError):
            logger.warning(
                "Failed to parse thought JSON, using raw text. Response: %s",
                response_text[:300],
            )
            thought_content = response_text.strip() or "Reflecting quietly..."
            mood = "contemplative"
            intensity = 0.5

        # Sanitize thought content — strip any remaining tags/markdown artifacts
        thought_content = _sanitize_thought(thought_content)

        metadata: dict[str, str] = {}
        if is_goal_oriented:
            metadata = {
                "topic": topic,
                "follow_up": follow_up,
                "new_goal": new_goal,
                "goal_updates": json.dumps(goal_updates_raw),
                "workshop_worthy": workshop_worthy_raw,
            }

        thought = Thought(
            id=str(uuid.uuid4()),
            content=thought_content,
            source="autonomous",
            thought_type=thought_type,
            created_at=datetime.utcnow(),
            metadata=metadata,
        )

        if tool_results_context:
            thought.metadata["used_tools"] = "true"

        return thought, mood, max(0.0, min(1.0, intensity))
