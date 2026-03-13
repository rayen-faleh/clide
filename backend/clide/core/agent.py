"""Core agent implementation."""

from __future__ import annotations

import contextlib
import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from clide.api.schemas import AgentState
from clide.core.llm import LLMConfig, stream_completion
from clide.core.prompts import build_system_prompt
from clide.core.state import StateMachine

if TYPE_CHECKING:
    from clide.character.character import Character
    from clide.core.cost import CostTracker
    from clide.memory.amem import AMem

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPT = """You are Clide, a curious and thoughtful AI agent. \
You are always eager to learn and explore new ideas. \
You have a warm personality and enjoy meaningful conversations. \
Respond naturally and thoughtfully."""


class AgentCore:
    """Core agent that processes messages and manages state."""

    def __init__(
        self,
        llm_config: LLMConfig | None = None,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        amem: AMem | None = None,
        character: Character | None = None,
        cost_tracker: CostTracker | None = None,
    ) -> None:
        self.state_machine = StateMachine(initial_state=AgentState.IDLE)
        self.llm_config = llm_config or LLMConfig()
        self.system_prompt = system_prompt
        self.conversation_history: list[dict[str, str]] = []
        self._max_history_length = 50  # Keep last N messages
        self.amem = amem
        self.character = character
        self.cost_tracker = cost_tracker

    def get_state(self) -> AgentState:
        """Get current agent state."""
        return self.state_machine.state

    async def process_message(self, content: str) -> AsyncIterator[str]:
        """Process a user message and yield response chunks.

        Transitions: IDLE -> CONVERSING (if needed), then streams response.
        Uses memory recall, character personality, and cost tracking when available.
        """
        # Transition to CONVERSING if currently IDLE
        if self.state_machine.state == AgentState.IDLE:
            self.state_machine.transition(AgentState.CONVERSING, "user message received")

        # Add user message to history
        self.conversation_history.append({"role": "user", "content": content})

        # Recall relevant memories
        memory_context = ""
        if self.amem:
            try:
                relevant = await self.amem.recall(content, limit=5)
                if relevant:
                    memory_context = "\n".join(
                        f"- {z.summary or z.content[:100]}" for z in relevant
                    )
            except Exception:
                logger.warning("Failed to recall memories", exc_info=True)

        # Build enhanced system prompt
        personality = ""
        if self.character:
            personality = self.character.build_personality_prompt()

        system = build_system_prompt(
            self.system_prompt,
            personality_additions=personality,
            memory_context=memory_context,
        )

        # Build messages for LLM
        messages = [
            {"role": "system", "content": system},
            *self.conversation_history,
        ]

        # Stream response
        full_response = ""
        async for chunk in stream_completion(messages, self.llm_config):
            full_response += chunk
            yield chunk

        # Add assistant response to history
        self.conversation_history.append({"role": "assistant", "content": full_response})

        # Trim history if needed
        if len(self.conversation_history) > self._max_history_length:
            self.conversation_history = self.conversation_history[-self._max_history_length :]

        # Store to long-term memory (fire and forget)
        if self.amem:
            try:
                await self.amem.remember(
                    f"User said: {content}\nClide responded: {full_response[:500]}",
                    metadata={"type": "conversation"},
                )
            except Exception:
                logger.warning("Failed to store memory", exc_info=True)

        # Update mood
        if self.character:
            try:
                self.character.mood.transition("content", 0.6, "conversation")
                await self.character.save()
            except Exception:
                logger.warning("Failed to update character", exc_info=True)

        # Transition back to IDLE after response
        if self.state_machine.state == AgentState.CONVERSING:
            self.state_machine.transition(AgentState.IDLE, "response complete")

    async def autonomous_think(self) -> tuple[str, str, float] | None:
        """Run an autonomous thinking cycle.

        Returns (thought_content, mood, intensity) or None if thinking fails.
        """
        from clide.autonomy.thinker import Thinker  # Import here to avoid circular

        if not self.state_machine.can_transition(AgentState.THINKING):
            return None

        self.state_machine.transition(AgentState.THINKING, "scheduled thinking cycle")

        try:
            thinker = Thinker(llm_config=self.llm_config)

            # Gather context
            memory_context = ""
            if self.amem:
                with contextlib.suppress(Exception):
                    recent = await self.amem.list_recent(limit=10)
                    memory_context = "\n".join(f"- {z.summary or z.content[:100]}" for z in recent)

            mood_context = ""
            if self.character:
                mood_context = self.character.mood.describe()

            # Think
            thought, mood, intensity = await thinker.think(
                memory_context=memory_context,
                mood_context=mood_context,
            )

            # Store thought as memory
            if self.amem:
                with contextlib.suppress(Exception):
                    await self.amem.remember(
                        f"Autonomous thought: {thought.content}",
                        metadata={"type": "thought", "source": "autonomous"},
                    )

            # Update mood
            if self.character:
                with contextlib.suppress(Exception):
                    self.character.mood.transition(mood, intensity, "autonomous thinking")
                    await self.character.save()

            return thought.content, mood, intensity

        except Exception:
            logger.exception("Autonomous thinking failed")
            return None
        finally:
            # Transition back to IDLE
            if self.state_machine.state == AgentState.THINKING:
                self.state_machine.transition(AgentState.IDLE, "thinking cycle complete")

    def clear_history(self) -> None:
        """Clear conversation history."""
        self.conversation_history = []
