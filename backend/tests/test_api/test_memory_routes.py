"""Tests for memory API routes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from clide.api.memory_routes import (
    cost_router,
    memory_router,
    set_amem,
    set_cost_tracker,
)
from clide.core.cost import CostTracker, TokenUsage, UsagePurpose
from clide.memory.models import MemoryLink, Zettel


def _make_zettel(
    id: str = "z1",
    content: str = "Test content",
    summary: str = "Test summary",
    **kwargs: Any,
) -> Zettel:
    now = datetime.now(UTC)
    return Zettel(
        id=id,
        content=content,
        summary=summary,
        keywords=kwargs.get("keywords", ["test"]),
        tags=kwargs.get("tags", ["tag1"]),
        context=kwargs.get("context", "test context"),
        importance=kwargs.get("importance", 0.7),
        access_count=kwargs.get("access_count", 1),
        links=kwargs.get("links", []),
        created_at=kwargs.get("created_at", now),
        updated_at=kwargs.get("updated_at", now),
        metadata=kwargs.get("metadata", {}),
    )


def _create_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(memory_router)
    app.include_router(cost_router)
    return app


@pytest.fixture
def mock_amem() -> AsyncMock:
    amem = AsyncMock()
    set_amem(amem)  # type: ignore[arg-type]
    return amem


@pytest.fixture
def mock_cost_tracker() -> CostTracker:
    tracker = CostTracker(daily_token_limit=10000)
    set_cost_tracker(tracker)
    return tracker


@pytest.fixture
async def client(mock_amem: AsyncMock, mock_cost_tracker: CostTracker) -> AsyncClient:
    app = _create_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac  # type: ignore[misc]


class TestListMemories:
    async def test_list_memories(self, client: AsyncClient, mock_amem: AsyncMock) -> None:
        mock_amem.list_recent.return_value = [
            _make_zettel(id="z1"),
            _make_zettel(id="z2"),
        ]
        response = await client.get("/api/memories")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert len(data["memories"]) == 2
        assert data["memories"][0]["id"] == "z1"

    async def test_list_memories_with_pagination(
        self, client: AsyncClient, mock_amem: AsyncMock
    ) -> None:
        mock_amem.list_recent.return_value = [_make_zettel(id="z3")]
        response = await client.get("/api/memories?limit=10&offset=5")
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 10
        assert data["offset"] == 5
        mock_amem.list_recent.assert_called_once_with(limit=10, offset=5)


class TestSearchMemories:
    async def test_search_memories(self, client: AsyncClient, mock_amem: AsyncMock) -> None:
        mock_amem.recall.return_value = [_make_zettel(id="z1", summary="Found it")]
        response = await client.get("/api/memories/search?q=test+query")
        assert response.status_code == 200
        data = response.json()
        assert data["query"] == "test query"
        assert data["count"] == 1
        assert data["results"][0]["summary"] == "Found it"
        mock_amem.recall.assert_called_once_with("test query", limit=10, use_spreading=True)


class TestGetMemoryGraph:
    async def test_get_memory_graph(self, client: AsyncClient, mock_amem: AsyncMock) -> None:
        z1 = _make_zettel(
            id="z1",
            links=[
                MemoryLink(
                    source_id="z1",
                    target_id="z2",
                    relationship="related_to",
                    strength=0.8,
                )
            ],
        )
        z2 = _make_zettel(id="z2")
        mock_amem.list_recent.return_value = [z1, z2]
        mock_amem.get.side_effect = lambda mid: {
            "z1": z1,
            "z2": z2,
        }.get(mid)
        response = await client.get("/api/memories/graph?limit=100")
        assert response.status_code == 200
        data = response.json()
        assert data["node_count"] == 2
        assert data["edge_count"] == 1
        assert data["edges"][0]["source"] == "z1"
        assert data["edges"][0]["target"] == "z2"


class TestGetMemory:
    async def test_get_memory_by_id(self, client: AsyncClient, mock_amem: AsyncMock) -> None:
        z = _make_zettel(id="z1", content="Hello world")
        mock_amem.get.return_value = z
        response = await client.get("/api/memories/z1")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "z1"
        assert data["content"] == "Hello world"

    async def test_get_memory_not_found(self, client: AsyncClient, mock_amem: AsyncMock) -> None:
        mock_amem.get.return_value = None
        response = await client.get("/api/memories/nonexistent")
        assert response.status_code == 200
        data = response.json()
        assert data["error"] == "Memory not found"


class TestCostStats:
    async def test_cost_stats_endpoint(
        self, client: AsyncClient, mock_cost_tracker: CostTracker
    ) -> None:
        mock_cost_tracker.record(
            TokenUsage(
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
                purpose=UsagePurpose.CHAT,
            )
        )
        response = await client.get("/api/stats/costs")
        assert response.status_code == 200
        data = response.json()
        assert data["daily"]["total_tokens"] == 150
        assert data["budget"]["daily_limit"] == 10000
