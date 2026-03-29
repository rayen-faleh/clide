"""Shared context builder for cross-mode awareness."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..memory.amem import AMem
    from .event_log import EventLog

logger = logging.getLogger(__name__)


def format_age(dt: datetime | None) -> str:
    """Format a datetime as a human-readable relative age string."""
    if dt is None:
        return "unknown"
    now = datetime.now(UTC)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    age = now - dt
    if age.days > 0:
        return f"{age.days}d ago"
    elif age.seconds >= 3600:
        return f"{age.seconds // 3600}h ago"
    elif age.seconds >= 60:
        return f"{age.seconds // 60}m ago"
    else:
        return "just now"


@dataclass
class ContextResult:
    """Result of a context build operation."""

    memory_text: str
    cross_mode_text: str
    memories_used: int


_ALL_MODES = ("chat", "workshop", "thinking")
_CONTENT_LIMIT = 120
_TOOL_RESULT_LIMIT = 80


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _format_event(event: dict[str, Any]) -> str | None:
    """Format a single event dict into a concise one-line summary."""
    mode = event.get("mode", "")
    event_type = event.get("event_type", "")
    content = (event.get("content") or "").replace("\n", " ").strip()
    metadata = event.get("metadata") or {}

    if event_type == "user_message":
        return f"[{mode}] User: {_truncate(content, _CONTENT_LIMIT)}"
    elif event_type == "assistant_message":
        return f"[{mode}] You said: {_truncate(content, _CONTENT_LIMIT)}"
    elif event_type == "thought":
        return f"[thinking] You reflected: {_truncate(content, _CONTENT_LIMIT)}"
    elif event_type == "tool_call":
        tool_name = metadata.get("tool_name", content)
        return f"[{mode}] Used tool: {tool_name}"
    elif event_type == "tool_result":
        tool_name = metadata.get("tool_name", "")
        result_preview = _truncate(content, _TOOL_RESULT_LIMIT)
        return f"[{mode}] Tool result ({tool_name}): {result_preview}"
    elif event_type in ("workshop_plan", "workshop_step"):
        return f"[workshop] {_truncate(content, _CONTENT_LIMIT)}"
    elif event_type == "tool_checkpoint":
        return f"[{mode}] Checkpoint: {_truncate(content, _CONTENT_LIMIT)}"
    return None


class ContextBuilder:
    """Assembles cross-mode context from EventLog + A-MEM for any LLM call."""

    def __init__(self, event_log: EventLog, amem: AMem | None = None) -> None:
        self._event_log = event_log
        self._amem = amem

    async def build(
        self,
        query: str,
        current_mode: str,
        memory_limit: int = 5,
        event_limit: int = 8,
        include_modes: list[str] | None = None,
    ) -> ContextResult:
        """Build cross-mode context for an LLM call.

        Args:
            query: Semantic search query for A-MEM recall.
            current_mode: The mode making the request (excluded from cross-mode events by default).
            memory_limit: Max memories to recall from A-MEM.
            event_limit: Max cross-mode events to include from EventLog.
            include_modes: Explicit list of modes to pull events from.
                If None, defaults to all modes except current_mode.

        Returns:
            ContextResult with formatted memory and cross-mode text.
        """
        memory_text = ""
        memories_used = 0
        cross_mode_text = ""

        # 1. Memory recall via A-MEM
        if self._amem:
            try:
                zettels = await self._amem.recall(query, limit=memory_limit)
                if zettels:
                    memories_used = len(zettels)
                    memory_text = "\n".join(
                        f"- {z.summary or _truncate(z.content, _CONTENT_LIMIT)}"
                        f" [{format_age(z.created_at)}]"
                        for z in zettels
                    )
            except Exception:
                logger.warning("ContextBuilder: memory recall failed", exc_info=True)

        # 2. Cross-mode events from EventLog
        try:
            target_modes = include_modes or [
                m for m in _ALL_MODES if m != current_mode
            ]
            events: list[dict[str, Any]] = []
            for mode in target_modes:
                mode_events = await self._event_log.get_recent(
                    limit=event_limit, mode=mode
                )
                events.extend(mode_events)

            # Sort by created_at DESC and take top event_limit
            events.sort(key=lambda e: e.get("created_at", ""), reverse=True)
            events = events[:event_limit]

            lines: list[str] = []
            for event in events:
                line = _format_event(event)
                if line:
                    lines.append(f"- {line}")
            if lines:
                cross_mode_text = "\n".join(lines)
        except Exception:
            logger.warning("ContextBuilder: event log query failed", exc_info=True)

        return ContextResult(
            memory_text=memory_text,
            cross_mode_text=cross_mode_text,
            memories_used=memories_used,
        )
