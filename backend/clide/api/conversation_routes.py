"""Conversation history API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from clide.core.conversation_store import ConversationStore

conversation_router = APIRouter(prefix="/api/conversations", tags=["conversations"])

_store: ConversationStore | None = None


def set_conversation_store(store: ConversationStore) -> None:
    """Set the global conversation store instance."""
    global _store  # noqa: PLW0603
    _store = store


def get_conversation_store() -> ConversationStore:
    """Get the global conversation store instance."""
    if _store is None:
        raise RuntimeError("ConversationStore not initialized")
    return _store


@conversation_router.get("/recent")
async def get_recent_messages(
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """Get recent conversation messages."""
    store = get_conversation_store()
    messages = await store.get_recent(limit=limit)
    return {"messages": messages, "count": len(messages)}
