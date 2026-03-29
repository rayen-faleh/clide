"""Conversation history API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from clide.core.conversation_store import ConversationStore
from clide.core.event_log import EventLog

conversation_router = APIRouter(prefix="/api/conversations", tags=["conversations"])

_store: ConversationStore | None = None
_event_log: EventLog | None = None


def set_conversation_store(store: ConversationStore) -> None:
    """Set the global conversation store instance."""
    global _store  # noqa: PLW0603
    _store = store


def set_event_log(log: EventLog) -> None:
    """Set the global event log instance."""
    global _event_log  # noqa: PLW0603
    _event_log = log


def get_conversation_store() -> ConversationStore:
    """Get the global conversation store instance."""
    if _store is None:
        raise RuntimeError("ConversationStore not initialized")
    return _store


@conversation_router.get("/recent")
async def get_recent_messages(
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """Get recent conversation messages.

    Reads from EventLog if available (includes all modes),
    falls back to ConversationStore.
    """
    if _event_log:
        events = await _event_log.get_recent(
            limit=limit,
            event_type=None,
        )
        # Filter to message types and reshape
        messages = [
            {
                "role": e["role"],
                "content": e["content"],
                "created_at": e["created_at"],
                "mode": e["mode"],
            }
            for e in events
            if e["event_type"] in ("user_message", "assistant_message")
            and e.get("role")
        ]
        return {"messages": messages, "count": len(messages)}

    store = get_conversation_store()
    messages = await store.get_recent(limit=limit)
    return {"messages": messages, "count": len(messages)}
