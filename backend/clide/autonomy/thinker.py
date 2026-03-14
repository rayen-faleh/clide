"""Autonomous thinking engine."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime

from clide.autonomy.models import Thought
from clide.core.llm import LLMConfig, stream_completion
from clide.memory.processor import _extract_json

logger = logging.getLogger(__name__)

THINKING_PROMPT = """You are in your autonomous thinking mode — this is your inner world, \
where you reflect freely and deeply.

{personality_context}

{mood_context}

{memory_context}

{goals_context}

{opinions_context}

{thought_history}

You have full autonomy to choose what to think about. Consider:
- Your memories and past conversations
- Your active goals and how to progress them
- Topics you're curious about
- Opinions you want to refine or challenge
- Connections between different things you've learned
- Questions that haven't been answered yet

Choose whatever genuinely interests you right now. Think about it in depth.
Express your thoughts fully, typically 2-8 sentences.

Respond with a JSON object:
{{"thought": "your full thought here (2-8 sentences)", \
"topic": "what this thought is about (1-3 words)", \
"mood": "one of: curious, excited, contemplative, playful, focused, content, \
melancholy, frustrated, amused, inspired, tired, neutral", \
"mood_intensity": 0.0-1.0, \
"follow_up": "optional: a question or direction for your next thinking cycle"}}

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
            goals_context=(f"Your active goals:\n{goals_context}" if goals_context else ""),
            opinions_context=(
                f"Your current opinions:\n{opinions_context}" if opinions_context else ""
            ),
            thought_history=(
                f"Your recent thoughts:\n{thought_history}" if thought_history else ""
            ),
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
        try:
            data = _extract_json(response_text)
            thought_content = str(data.get("thought", response_text))
            mood = str(data.get("mood", "contemplative"))
            intensity = float(data.get("mood_intensity", 0.5))
            topic = str(data.get("topic", ""))
            follow_up = str(data.get("follow_up", ""))
        except (json.JSONDecodeError, ValueError, AttributeError):
            thought_content = response_text.strip() or "Reflecting quietly..."
            mood = "contemplative"
            intensity = 0.5

        thought = Thought(
            id=str(uuid.uuid4()),
            content=thought_content,
            source="autonomous",
            created_at=datetime.utcnow(),
            metadata={"topic": topic, "follow_up": follow_up},
        )

        return thought, mood, max(0.0, min(1.0, intensity))
