"""Autonomous thinking engine."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime

from clide.autonomy.models import Thought
from clide.core.llm import LLMConfig, stream_completion

logger = logging.getLogger(__name__)

THINKING_PROMPT = """You are in your autonomous thinking mode. \
Reflect on your recent memories and thoughts.

{memory_context}

{mood_context}

Generate a brief, genuine thought or reflection. It can be:
- A question you're curious about
- An insight connecting different things you've learned
- A creative idea or observation
- A reflection on a recent conversation

Keep it to 1-3 sentences. Be authentic and thoughtful.

Also, based on your reflection, suggest a mood update as JSON:
{{"thought": "your thought here", "mood": "one of: curious, excited, contemplative, \
playful, focused, content, inspired, amused", "mood_intensity": 0.0-1.0}}

Return ONLY the JSON."""


class Thinker:
    """Generates autonomous thoughts during thinking cycles."""

    def __init__(self, llm_config: LLMConfig | None = None) -> None:
        self.llm_config = llm_config or LLMConfig()

    async def think(
        self,
        memory_context: str = "",
        mood_context: str = "",
    ) -> tuple[Thought, str, float]:
        """Generate an autonomous thought.

        Returns:
            Tuple of (thought, suggested_mood, suggested_intensity)
        """
        prompt = THINKING_PROMPT.format(
            memory_context=(
                f"Recent memories:\n{memory_context}"
                if memory_context
                else "No recent memories yet."
            ),
            mood_context=f"Current mood: {mood_context}" if mood_context else "",
        )

        messages = [{"role": "user", "content": prompt}]
        response_text = ""
        async for chunk in stream_completion(messages, self.llm_config):
            response_text += chunk

        # Parse response
        try:
            data = json.loads(response_text)
            thought_content = str(data.get("thought", response_text))
            mood = str(data.get("mood", "contemplative"))
            intensity = float(data.get("mood_intensity", 0.5))
        except (json.JSONDecodeError, ValueError):
            thought_content = response_text.strip() or "Reflecting quietly..."
            mood = "contemplative"
            intensity = 0.5

        thought = Thought(
            id=str(uuid.uuid4()),
            content=thought_content,
            source="autonomous",
            created_at=datetime.utcnow(),
        )

        return thought, mood, max(0.0, min(1.0, intensity))
