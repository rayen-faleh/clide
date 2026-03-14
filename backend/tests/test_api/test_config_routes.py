"""Tests for configuration API routes."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from clide.api.config_routes import ConfigUpdate, _deep_merge, config_router
from clide.character.character import Character
from clide.character.traits import PersonalityTraits
from clide.core.agent import AgentCore
from clide.main import create_app


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    """Create a temporary config directory with agent.yaml."""
    agent_yaml = tmp_path / "agent.yaml"
    data: dict[str, Any] = {
        "agent": {
            "name": "Clide",
            "llm": {
                "provider": "anthropic",
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 4096,
            },
            "states": {
                "thinking": {"interval_seconds": 300, "max_consecutive_cycles": 5},
                "budget": {"daily_token_limit": 500000, "warning_threshold": 0.8},
            },
            "character": {
                "base_traits": {
                    "curiosity": 0.8,
                    "warmth": 0.7,
                    "humor": 0.5,
                    "assertiveness": 0.4,
                    "creativity": 0.7,
                }
            },
        }
    }
    with open(agent_yaml, "w") as f:
        yaml.dump(data, f)
    return tmp_path


@pytest.fixture
async def client(config_dir: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncClient:
    """Create a test client with patched config path."""
    import clide.api.config_routes as config_mod

    monkeypatch.setattr(config_mod, "CONFIG_PATH", config_dir / "agent.yaml")

    app = create_app()
    app.include_router(config_router)
    from clide.config.settings import Settings

    app.state.settings = Settings()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestGetConfig:
    async def test_get_config_returns_settings(self, client: AsyncClient) -> None:
        response = await client.get("/api/config")
        assert response.status_code == 200
        data = response.json()
        assert "agent" in data
        assert data["agent"]["name"] == "Clide"

    async def test_get_config_includes_traits(self, client: AsyncClient) -> None:
        response = await client.get("/api/config")
        data = response.json()
        traits = data["agent"]["character"]["base_traits"]
        assert traits["curiosity"] == 0.8
        assert traits["warmth"] == 0.7


class TestUpdateConfig:
    async def test_update_config_partial(self, client: AsyncClient) -> None:
        response = await client.patch(
            "/api/config",
            json={
                "agent": {
                    "character": {
                        "base_traits": {
                            "curiosity": 0.9,
                        }
                    }
                }
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["agent"]["character"]["base_traits"]["curiosity"] == 0.9
        # Other traits should remain unchanged
        assert data["agent"]["character"]["base_traits"]["warmth"] == 0.7

    async def test_update_config_invalid_rejected(self, client: AsyncClient) -> None:
        # Send an update with invalid data type for a known field
        response = await client.patch(
            "/api/config",
            json={
                "agent": {
                    "llm": {
                        "max_tokens": "not_a_number",
                    }
                }
            },
        )
        assert response.status_code == 400
        assert "Invalid configuration" in response.json()["detail"]


class TestToolsStatus:
    async def test_get_tools_status_empty(
        self, client: AsyncClient, config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When no tools.yaml exists, return empty list."""
        import clide.api.config_routes as config_mod

        monkeypatch.setattr(config_mod, "TOOLS_PATH", config_dir / "tools.yaml")
        response = await client.get("/api/config/tools/status")
        assert response.status_code == 200
        data = response.json()
        assert data["tools"] == []
        assert data["count"] == 0

    async def test_get_tools_status_with_tools(
        self, client: AsyncClient, config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When tools.yaml has tools, return them."""
        import clide.api.config_routes as config_mod

        tools_yaml = config_dir / "tools.yaml"
        tools_data = {
            "tools": [
                {"name": "web_search", "description": "Search the web", "enabled": True},
                {"name": "file_reader", "description": "Read files", "enabled": False},
            ]
        }
        with open(tools_yaml, "w") as f:
            yaml.dump(tools_data, f)

        monkeypatch.setattr(config_mod, "TOOLS_PATH", tools_yaml)

        response = await client.get("/api/config/tools/status")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert data["tools"][0]["name"] == "web_search"
        assert data["tools"][0]["status"] == "available"
        assert data["tools"][1]["name"] == "file_reader"
        assert data["tools"][1]["status"] == "disabled"


class TestDeepMerge:
    def test_deep_merge_simple(self) -> None:
        base: dict[str, Any] = {"a": 1, "b": 2}
        override: dict[str, Any] = {"b": 3, "c": 4}
        _deep_merge(base, override)
        assert base == {"a": 1, "b": 3, "c": 4}

    def test_deep_merge_nested(self) -> None:
        base: dict[str, Any] = {"a": {"x": 1, "y": 2}, "b": 3}
        override: dict[str, Any] = {"a": {"y": 99, "z": 100}}
        _deep_merge(base, override)
        assert base == {"a": {"x": 1, "y": 99, "z": 100}, "b": 3}

    def test_deep_merge_override_non_dict(self) -> None:
        base: dict[str, Any] = {"a": {"x": 1}}
        override: dict[str, Any] = {"a": "replaced"}
        _deep_merge(base, override)
        assert base == {"a": "replaced"}


class TestConfigUpdateModel:
    def test_config_update_accepts_none(self) -> None:
        update = ConfigUpdate()
        assert update.agent is None

    def test_config_update_accepts_dict(self) -> None:
        update = ConfigUpdate(agent={"name": "NewName"})
        assert update.agent == {"name": "NewName"}


class TestLiveAgentUpdate:
    """Tests that PATCH /api/config applies changes to the live agent core."""

    async def test_update_system_prompt_applies_to_live_agent(self, client: AsyncClient) -> None:
        agent_core = AgentCore(system_prompt="old prompt")
        with patch("clide.api.config_routes.get_agent_core", return_value=agent_core):
            response = await client.patch(
                "/api/config",
                json={"agent": {"system_prompt": "new live prompt"}},
            )
        assert response.status_code == 200
        assert agent_core.system_prompt == "new live prompt"

    async def test_update_traits_applies_to_live_agent(
        self, client: AsyncClient, tmp_path: Path
    ) -> None:
        character = Character(
            traits=PersonalityTraits(curiosity=0.5, warmth=0.5),
            db_path=tmp_path / "char.db",
        )
        character.save = AsyncMock()  # type: ignore[method-assign]
        agent_core = AgentCore(character=character)
        with patch("clide.api.config_routes.get_agent_core", return_value=agent_core):
            response = await client.patch(
                "/api/config",
                json={"agent": {"character": {"base_traits": {"curiosity": 0.95, "warmth": 0.3}}}},
            )
        assert response.status_code == 200
        assert agent_core.character.traits.curiosity == 0.95
        assert agent_core.character.traits.warmth == 0.3
        character.save.assert_awaited_once()

    async def test_live_update_failure_does_not_crash_endpoint(self, client: AsyncClient) -> None:
        with patch(
            "clide.api.config_routes.get_agent_core",
            side_effect=RuntimeError("no agent"),
        ):
            response = await client.patch(
                "/api/config",
                json={"agent": {"system_prompt": "test"}},
            )
        # Should still return 200 — YAML was saved successfully
        assert response.status_code == 200
