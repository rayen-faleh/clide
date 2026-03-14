"""LLM integration via litellm."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import litellm

logger = logging.getLogger(__name__)

# Module-level semaphore: max 2 concurrent LLM calls
_llm_semaphore = asyncio.Semaphore(2)


@dataclass
class LLMConfig:
    """LLM configuration."""

    provider: str = "ollama"
    model: str = "llama3.2"
    max_tokens: int = 4096
    api_base: str = ""
    timeout_seconds: float = 600.0  # 10 minutes default


def _build_model_name(config: LLMConfig) -> str:
    """Build the litellm model name from config."""
    # litellm uses format: provider/model
    if config.provider == "anthropic":
        return config.model
    return f"{config.provider}/{config.model}"


async def stream_completion(
    messages: list[dict[str, str]],
    config: LLMConfig,
    **kwargs: Any,
) -> AsyncIterator[str]:
    """Stream completion tokens from the LLM.

    Args:
        messages: List of message dicts with 'role' and 'content'
        config: LLM configuration
        **kwargs: Additional arguments passed to litellm

    Yields:
        String chunks of the response

    Raises:
        TimeoutError: If the initial LLM connection times out
    """
    model = _build_model_name(config)
    logger.debug("Streaming completion with model: %s", model)

    call_kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": config.max_tokens,
        "stream": True,
        **kwargs,
    }
    if config.api_base:
        call_kwargs["api_base"] = config.api_base

    async with _llm_semaphore:
        # Timeout only on the initial connection, not on streaming
        try:
            async with asyncio.timeout(config.timeout_seconds):
                response = await litellm.acompletion(**call_kwargs)
        except TimeoutError:
            logger.error("LLM call timed out after %ss", config.timeout_seconds)
            raise

        # Stream without timeout (tokens arrive at their own pace)
        # Handle "thinking" models (e.g., qwen3.5) that split output into
        # reasoning_content (internal thinking) and content (actual response).
        # We yield content tokens, and if there are none, fall back to
        # reasoning_content so the response isn't empty.
        chunk_count = 0
        reasoning_chunks: list[str] = []
        async for chunk in response:
            delta = chunk.choices[0].delta
            content = delta.content
            reasoning = getattr(delta, "reasoning_content", None)

            if content:
                chunk_count += 1
                yield content
            elif reasoning:
                reasoning_chunks.append(reasoning)

        # If the model only produced reasoning (thinking mode), yield that
        # as the response so the user isn't left with an empty message.
        if chunk_count == 0 and reasoning_chunks:
            logger.info(
                "LLM produced only reasoning tokens (%d chunks), yielding as response",
                len(reasoning_chunks),
            )
            for rc in reasoning_chunks:
                yield rc
        elif chunk_count == 0:
            logger.warning("LLM stream produced 0 content chunks")
        else:
            logger.debug("LLM stream complete: %d chunks yielded", chunk_count)
