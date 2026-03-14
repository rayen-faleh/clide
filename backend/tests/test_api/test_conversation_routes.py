"""Tests for conversation history API routes."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from clide.api.conversation_routes import conversation_router, set_conversation_store
from clide.core.conversation_store import ConversationStore


def _create_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(conversation_router)
    return app


@pytest.fixture
async def client(tmp_path: Path) -> AsyncClient:  # type: ignore[misc]
    store = ConversationStore(db_path=tmp_path / "test.db")
    set_conversation_store(store)
    app = _create_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac  # type: ignore[misc]


class TestConversationRoutes:
    async def test_get_recent_empty(self, client: AsyncClient) -> None:
        response = await client.get("/api/conversations/recent")
        assert response.status_code == 200
        data = response.json()
        assert data["messages"] == []
        assert data["count"] == 0

    async def test_get_recent_with_messages(self, client: AsyncClient, tmp_path: Path) -> None:
        # Add messages via the store directly
        store = ConversationStore(db_path=tmp_path / "test.db")
        set_conversation_store(store)
        await store.add_message("user", "hello")
        await store.add_message("assistant", "hi there")

        response = await client.get("/api/conversations/recent")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert data["messages"][0]["role"] == "user"
        assert data["messages"][0]["content"] == "hello"
        assert data["messages"][1]["role"] == "assistant"
        assert data["messages"][1]["content"] == "hi there"

    async def test_get_recent_with_limit(self, client: AsyncClient, tmp_path: Path) -> None:
        store = ConversationStore(db_path=tmp_path / "test.db")
        set_conversation_store(store)
        for i in range(5):
            await store.add_message("user", f"msg {i}")

        response = await client.get("/api/conversations/recent?limit=2")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
