"""Tests for the agent core."""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import patch

import pytest

from clide.api.schemas import AgentState
from clide.core.agent import AgentCore


async def fake_stream_completion(
    messages: list[dict[str, str]], config: object, **kwargs: object
) -> AsyncIterator[str]:
    for chunk in ["Hello", " there", "!"]:
        yield chunk


class TestAgentCore:
    def test_initial_state_is_idle(self) -> None:
        agent = AgentCore()
        assert agent.get_state() == AgentState.IDLE

    @pytest.mark.asyncio
    async def test_process_message_transitions_to_conversing(self) -> None:
        agent = AgentCore()
        with patch("clide.core.agent.stream_completion", side_effect=fake_stream_completion):
            async for _ in agent.process_message("hi"):
                pass
        assert agent.get_state() == AgentState.CONVERSING

    @pytest.mark.asyncio
    async def test_process_message_adds_to_history(self) -> None:
        agent = AgentCore()
        with patch("clide.core.agent.stream_completion", side_effect=fake_stream_completion):
            async for _ in agent.process_message("hi"):
                pass
        assert len(agent.conversation_history) == 2
        assert agent.conversation_history[0]["role"] == "user"
        assert agent.conversation_history[0]["content"] == "hi"
        assert agent.conversation_history[1]["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_process_message_streams_response(self) -> None:
        agent = AgentCore()
        chunks: list[str] = []
        with patch("clide.core.agent.stream_completion", side_effect=fake_stream_completion):
            async for chunk in agent.process_message("hi"):
                chunks.append(chunk)
        assert chunks == ["Hello", " there", "!"]

    @pytest.mark.asyncio
    async def test_conversation_history_accumulates(self) -> None:
        agent = AgentCore()
        with patch("clide.core.agent.stream_completion", side_effect=fake_stream_completion):
            async for _ in agent.process_message("first"):
                pass
            async for _ in agent.process_message("second"):
                pass
        assert len(agent.conversation_history) == 4
        assert agent.conversation_history[0]["content"] == "first"
        assert agent.conversation_history[2]["content"] == "second"

    def test_clear_history(self) -> None:
        agent = AgentCore()
        agent.conversation_history = [{"role": "user", "content": "test"}]
        agent.clear_history()
        assert agent.conversation_history == []

    @pytest.mark.asyncio
    async def test_history_trimming_at_max_length(self) -> None:
        agent = AgentCore()
        agent._max_history_length = 4  # noqa: SLF001

        with patch("clide.core.agent.stream_completion", side_effect=fake_stream_completion):
            for i in range(5):
                async for _ in agent.process_message(f"msg {i}"):
                    pass

        # Should be trimmed to last 4 entries
        assert len(agent.conversation_history) == 4
