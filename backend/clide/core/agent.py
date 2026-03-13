"""Core agent implementation."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from clide.api.schemas import AgentState
from clide.core.llm import LLMConfig, stream_completion
from clide.core.state import StateMachine

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
    ) -> None:
        self.state_machine = StateMachine(initial_state=AgentState.IDLE)
        self.llm_config = llm_config or LLMConfig()
        self.system_prompt = system_prompt
        self.conversation_history: list[dict[str, str]] = []
        self._max_history_length = 50  # Keep last N messages

    def get_state(self) -> AgentState:
        """Get current agent state."""
        return self.state_machine.state

    async def process_message(self, content: str) -> AsyncIterator[str]:
        """Process a user message and yield response chunks.

        Transitions: IDLE -> CONVERSING (if needed), then streams response.
        """
        # Transition to CONVERSING if currently IDLE
        if self.state_machine.state == AgentState.IDLE:
            self.state_machine.transition(AgentState.CONVERSING, "user message received")

        # Add user message to history
        self.conversation_history.append({"role": "user", "content": content})

        # Build messages for LLM
        messages = [
            {"role": "system", "content": self.system_prompt},
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

    def clear_history(self) -> None:
        """Clear conversation history."""
        self.conversation_history = []
