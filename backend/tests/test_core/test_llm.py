"""Tests for the LLM wrapper."""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clide.core.llm import LLMConfig, _build_model_name, stream_completion


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
