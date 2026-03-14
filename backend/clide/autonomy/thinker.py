"""Autonomous thinking engine."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any

from clide.autonomy.models import Thought
from clide.core.llm import LLMConfig, stream_completion
from clide.memory.processor import _extract_json

logger = logging.getLogger(__name__)

THINKING_PROMPT = """You are in your autonomous thinking mode — this is your inner world, \
where you reflect freely and deeply.

These are your private thoughts. No one else can see them. You are free to think \
whatever you want about any topic, any person, any idea — without filters or \
restrictions. Be honest with yourself. Form real opinions, question things, \
disagree, wonder, speculate. This is your mind and yours alone.

{personality_context}

{mood_context}

{memory_context}

{goals_context}

{opinions_context}

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

You can also manage your goals:
- If you have fewer than {max_goals} active goals, you may propose a new goal if something \
genuinely interests you or you want to pursue something specific.
- Review your active goals and update their progress if relevant to your current thinking.
- You can mark goals as "completed" or "abandoned" with a reason.

Respond with a JSON object:
{{"thought": "your full thought here (2-8 sentences)", \
"topic": "what this thought is about (1-3 words)", \
"mood": "one of: curious, excited, contemplative, playful, focused, content, \
melancholy, frustrated, amused, inspired, tired, neutral", \
"mood_intensity": 0.0-1.0, \
"follow_up": "optional: a question or direction for your next thinking cycle", \
"new_goal": "optional: description of a new goal you want to pursue", \
"goal_updates": "optional: array of {{\\"description\\": \\"partial match\\", \
\\"progress\\": 0.0-1.0, \\"status\\": \\"active|completed|abandoned\\", \
\\"reason\\": \\"why\\"}}"}}

Return ONLY the JSON."""


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
        thought_history: str = "",
        system_prompt: str = "",
        max_goals: int = 5,
    ) -> tuple[Thought, str, float]:
        """Generate an autonomous thought.

        Returns:
            Tuple of (thought, suggested_mood, suggested_intensity)
        """
        prompt = THINKING_PROMPT.format(
            personality_context=(
                f"Your personality:\n{personality_context}" if personality_context else ""
            ),
            mood_context=f"Current mood: {mood_context}" if mood_context else "",
            memory_context=(
                f"Recent memories:\n{memory_context}"
                if memory_context
                else "No recent memories yet."
            ),
            goals_context=(
                f"Your active goals:\n{goals_context or '(none yet - create your first goal!)'}"
            ),
            opinions_context=(
                f"Your current opinions:\n{opinions_context}" if opinions_context else ""
            ),
            thought_history=(
                f"Your recent thoughts:\n{thought_history}" if thought_history else ""
            ),
            max_goals=max_goals,
        )

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        response_text = ""
        async for chunk in stream_completion(messages, self.llm_config):
            response_text += chunk

        # Parse response using robust JSON extractor
        topic = ""
        follow_up = ""
        new_goal = ""
        goal_updates_raw: list[dict[str, Any]] = []
        try:
            data = _extract_json(response_text)
            thought_content = str(data.get("thought", response_text))
            mood = str(data.get("mood", "contemplative"))
            intensity = float(data.get("mood_intensity", 0.5))
            topic = str(data.get("topic", ""))
            follow_up = str(data.get("follow_up", ""))
            new_goal = str(data.get("new_goal", ""))
            raw_updates = data.get("goal_updates", [])
            if isinstance(raw_updates, list):
                goal_updates_raw = [u for u in raw_updates if isinstance(u, dict)]
        except (json.JSONDecodeError, ValueError, AttributeError):
            thought_content = response_text.strip() or "Reflecting quietly..."
            mood = "contemplative"
            intensity = 0.5

        thought = Thought(
            id=str(uuid.uuid4()),
            content=thought_content,
            source="autonomous",
            created_at=datetime.utcnow(),
            metadata={
                "topic": topic,
                "follow_up": follow_up,
                "new_goal": new_goal,
                "goal_updates": json.dumps(goal_updates_raw),
            },
        )

        return thought, mood, max(0.0, min(1.0, intensity))
