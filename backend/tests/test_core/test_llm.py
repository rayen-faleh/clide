"""Tests for the LLM wrapper."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clide.core.llm import (
    LLMConfig,
    _build_model_name,
    _llm_semaphore,
    complete_with_tools,
    stream_completion,
)


class MockChunk:
    def __init__(self, content: str | None) -> None:
        self.choices = [MagicMock(delta=MagicMock(content=content))]


async def mock_stream(chunks: list[str]) -> AsyncIterator[MockChunk]:
    for chunk in chunks:
        yield MockChunk(chunk)


class TestBuildModelName:
    def test_build_model_name_anthropic(self) -> None:
        config = LLMConfig(provider="anthropic", model="claude-sonnet-4-20250514")
        assert _build_model_name(config) == "claude-sonnet-4-20250514"

    def test_build_model_name_other_provider(self) -> None:
        config = LLMConfig(provider="openai", model="gpt-4")
        assert _build_model_name(config) == "openai/gpt-4"


class TestLLMConfig:
    def test_default_timeout_seconds(self) -> None:
        config = LLMConfig()
        assert config.timeout_seconds == 600.0

    def test_custom_timeout_seconds(self) -> None:
        config = LLMConfig(timeout_seconds=30.0)
        assert config.timeout_seconds == 30.0


class TestStreamCompletion:
    @pytest.mark.asyncio
    async def test_stream_completion_yields_chunks(self) -> None:
        config = LLMConfig()
        messages = [{"role": "user", "content": "hello"}]

        mock_response = mock_stream(["Hello", " world", "!"])

        with patch("clide.core.llm.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)

            chunks: list[str] = []
            async for chunk in stream_completion(messages, config):
                chunks.append(chunk)

        assert chunks == ["Hello", " world", "!"]

    @pytest.mark.asyncio
    async def test_stream_completion_skips_none_content(self) -> None:
        config = LLMConfig()
        messages = [{"role": "user", "content": "hello"}]

        async def mixed_stream() -> AsyncIterator[MockChunk]:
            yield MockChunk("Hello")
            yield MockChunk(None)
            yield MockChunk(" world")

        with patch("clide.core.llm.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mixed_stream())

            chunks: list[str] = []
            async for chunk in stream_completion(messages, config):
                chunks.append(chunk)

        assert chunks == ["Hello", " world"]

    @pytest.mark.asyncio
    async def test_stream_completion_timeout(self) -> None:
        config = LLMConfig(timeout_seconds=0.01)
        messages = [{"role": "user", "content": "hello"}]

        async def slow_completion(**kwargs: object) -> object:
            await asyncio.sleep(10)
            return mock_stream(["late"])

        with patch("clide.core.llm.litellm") as mock_litellm:
            mock_litellm.acompletion = slow_completion

            with pytest.raises(TimeoutError):
                async for _ in stream_completion(messages, config):
                    pass

    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrency(self) -> None:
        """Verify that at most 2 LLM calls run concurrently."""
        config = LLMConfig()
        messages = [{"role": "user", "content": "hello"}]

        max_concurrent = 0
        current_concurrent = 0
        lock = asyncio.Lock()

        async def tracked_completion(**kwargs: object) -> AsyncIterator[MockChunk]:
            nonlocal max_concurrent, current_concurrent
            async with lock:
                current_concurrent += 1
                if current_concurrent > max_concurrent:
                    max_concurrent = current_concurrent
            await asyncio.sleep(0.05)
            async with lock:
                current_concurrent -= 1
            return mock_stream(["ok"])  # type: ignore[return-value]

        with patch("clide.core.llm.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(side_effect=tracked_completion)

            async def consume(idx: int) -> None:
                async for _ in stream_completion(messages, config):
                    pass

            # Launch 4 concurrent calls; semaphore should limit to 2
            await asyncio.gather(consume(0), consume(1), consume(2), consume(3))

        assert max_concurrent <= 2

    def test_semaphore_is_module_level(self) -> None:
        assert isinstance(_llm_semaphore, asyncio.Semaphore)


class TestCompleteWithTools:
    @pytest.mark.asyncio
    async def test_calls_acompletion_with_tools_and_no_stream(self) -> None:
        config = LLMConfig()
        messages: list[dict[str, object]] = [{"role": "user", "content": "hello"}]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search",
                    "parameters": {},
                },
            }
        ]

        mock_response = MagicMock()
        with patch("clide.core.llm.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)

            result = await complete_with_tools(messages, config, tools)

        assert result is mock_response
        call_kwargs = mock_litellm.acompletion.call_args[1]
        assert call_kwargs["tools"] == tools
        assert call_kwargs["stream"] is False

    @pytest.mark.asyncio
    async def test_respects_semaphore(self) -> None:
        config = LLMConfig()
        messages: list[dict[str, object]] = [{"role": "user", "content": "hello"}]
        tools: list[dict[str, object]] = [
            {"type": "function", "function": {"name": "t", "description": "", "parameters": {}}}
        ]

        max_concurrent = 0
        current_concurrent = 0
        lock = asyncio.Lock()

        async def tracked_completion(**kwargs: object) -> MagicMock:
            nonlocal max_concurrent, current_concurrent
            async with lock:
                current_concurrent += 1
                if current_concurrent > max_concurrent:
                    max_concurrent = current_concurrent
            await asyncio.sleep(0.05)
            async with lock:
                current_concurrent -= 1
            return MagicMock()

        with (
            patch("clide.core.llm._llm_semaphore", asyncio.Semaphore(2)),
            patch("clide.core.llm.litellm") as mock_litellm,
        ):
            mock_litellm.acompletion = AsyncMock(side_effect=tracked_completion)

            await asyncio.gather(
                complete_with_tools(messages, config, tools),
                complete_with_tools(messages, config, tools),
                complete_with_tools(messages, config, tools),
                complete_with_tools(messages, config, tools),
            )

        assert max_concurrent <= 2

    @pytest.mark.asyncio
    async def test_respects_timeout(self) -> None:
        config = LLMConfig(timeout_seconds=0.01)
        messages: list[dict[str, object]] = [{"role": "user", "content": "hello"}]
        tools: list[dict[str, object]] = [
            {"type": "function", "function": {"name": "t", "description": "", "parameters": {}}}
        ]

        async def slow_completion(**kwargs: object) -> MagicMock:
            await asyncio.sleep(10)
            return MagicMock()

        with patch("clide.core.llm.litellm") as mock_litellm:
            mock_litellm.acompletion = slow_completion

            with pytest.raises(TimeoutError):
                await complete_with_tools(messages, config, tools)
