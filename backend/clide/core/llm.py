"""LLM integration via litellm."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import litellm

logger = logging.getLogger(__name__)


@dataclass
class LLMConfig:
    """LLM configuration."""

    provider: str = "ollama"
    model: str = "llama3.2"
    max_tokens: int = 4096
    api_base: str = ""


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

    response = await litellm.acompletion(**call_kwargs)

    async for chunk in response:
        content = chunk.choices[0].delta.content
        if content:
            yield content
