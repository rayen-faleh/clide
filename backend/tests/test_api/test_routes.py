"""Tests for HTTP API routes."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from clide.config.settings import Settings
from clide.main import create_app


@pytest.fixture
async def client():
    app = create_app()
    # Manually set settings since httpx doesn't run lifespan
    app.state.settings = Settings()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestHealthEndpoint:
    async def test_health_endpoint_returns_ok(self, client: AsyncClient) -> None:
        response = await client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    async def test_health_endpoint_includes_agent_name(self, client: AsyncClient) -> None:
        response = await client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert "agent_name" in data
        assert isinstance(data["agent_name"], str)
        assert len(data["agent_name"]) > 0
