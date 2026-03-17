"""Tests for workshop REST API routes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from clide.api.workshop_routes import (
    set_agent_core,
    workshop_router,
)


@pytest.fixture
def _reset_agent_core() -> None:
    """Reset the module-level _agent_core before each test."""
    set_agent_core(None)


class TestWorkshopRoutes:
    """Tests for workshop API endpoints."""

    def test_get_session_no_agent(self, _reset_agent_core: None) -> None:
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(workshop_router)
        client = TestClient(app)

        response = client.get("/api/workshop/session")
        assert response.status_code == 200
        assert response.json() == {"session": None}

    def test_get_session_no_active_session(self, _reset_agent_core: None) -> None:
        from fastapi import FastAPI

        mock_agent = MagicMock()
        mock_agent.get_workshop_session.return_value = None
        set_agent_core(mock_agent)

        app = FastAPI()
        app.include_router(workshop_router)
        client = TestClient(app)

        response = client.get("/api/workshop/session")
        assert response.status_code == 200
        assert response.json() == {"session": None}

    def test_get_session_with_active_session(self, _reset_agent_core: None) -> None:
        from datetime import UTC, datetime

        from fastapi import FastAPI

        mock_session = MagicMock()
        mock_session.id = "sess-123"
        mock_session.goal_description = "Test goal"
        mock_session.status = "active"
        mock_session.current_step_index = 0
        mock_session.plan = None
        mock_session.inner_dialogue = [{"role": "assistant", "content": "thinking..."}]
        mock_session.created_at = datetime(2026, 1, 1, tzinfo=UTC)

        mock_agent = MagicMock()
        mock_agent.get_workshop_session.return_value = mock_session
        set_agent_core(mock_agent)

        app = FastAPI()
        app.include_router(workshop_router)
        client = TestClient(app)

        response = client.get("/api/workshop/session")
        assert response.status_code == 200
        data = response.json()
        assert data["session"]["id"] == "sess-123"
        assert data["session"]["goal_description"] == "Test goal"
        assert data["session"]["status"] == "active"
        assert data["session"]["plan"] is None

    def test_discard_no_agent(self, _reset_agent_core: None) -> None:
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(workshop_router)
        client = TestClient(app)

        response = client.post("/api/workshop/discard")
        assert response.status_code == 200
        assert response.json() == {"error": "Agent not initialized"}

    def test_discard_with_agent(self, _reset_agent_core: None) -> None:
        from fastapi import FastAPI

        mock_agent = MagicMock()
        mock_agent.discard_workshop = AsyncMock()
        set_agent_core(mock_agent)

        app = FastAPI()
        app.include_router(workshop_router)
        client = TestClient(app)

        response = client.post("/api/workshop/discard")
        assert response.status_code == 200
        assert response.json() == {"status": "discarded"}
        mock_agent.discard_workshop.assert_called_once()
