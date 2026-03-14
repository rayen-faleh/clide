"""Tests for tool registry."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clide.tools.models import ToolDefinition, ToolStatus
from clide.tools.registry import ToolRegistry


@pytest.fixture
def empty_yaml(tmp_path: Path) -> Path:
    p = tmp_path / "tools.yaml"
    p.write_text("tools: []\n")
    return p


@pytest.fixture
def valid_yaml(tmp_path: Path) -> Path:
    p = tmp_path / "tools.yaml"
    p.write_text(
        """\
tools:
  - name: search
    command: python
    args: ["-m", "search_server"]
    env:
      API_KEY: "test-key"
    enabled: true
    description: "Search tool server"
  - name: calc
    command: node
    args: ["calc.js"]
"""
    )
    return p


@pytest.fixture
def yaml_with_transport(tmp_path: Path) -> Path:
    p = tmp_path / "tools.yaml"
    p.write_text(
        """\
tools:
  - name: search
    transport: sse
    command: python
    args: []
  - name: calc
    command: node
    args: []
"""
    )
    return p


class TestRegistryFromYaml:
    def test_empty_tools(self, empty_yaml: Path) -> None:
        registry = ToolRegistry.from_yaml(empty_yaml)
        assert registry.server_count == 0
        assert registry.tool_count == 0

    def test_missing_file(self, tmp_path: Path) -> None:
        registry = ToolRegistry.from_yaml(tmp_path / "nonexistent.yaml")
        assert registry.server_count == 0

    def test_with_servers(self, valid_yaml: Path) -> None:
        registry = ToolRegistry.from_yaml(valid_yaml)
        assert registry.server_count == 2

    def test_default_path_uses_project_root(self) -> None:
        """Verify that from_yaml() with no args uses _PROJECT_ROOT."""
        with patch("clide.tools.registry._PROJECT_ROOT", Path("/fake/root")):
            registry = ToolRegistry.from_yaml()
            # File won't exist so we get an empty registry, but the path is resolved
            assert registry.server_count == 0

    def test_transport_field_parsed_from_yaml(self, yaml_with_transport: Path) -> None:
        """Verify transport field is read from YAML config."""
        registry = ToolRegistry.from_yaml(yaml_with_transport)
        assert registry.server_count == 2

        # Check that the transport was parsed correctly
        search_client = registry._servers["search"]
        calc_client = registry._servers["calc"]
        assert search_client.config.transport == "sse"
        assert calc_client.config.transport == "stdio"  # default

    def test_transport_defaults_to_stdio(self, valid_yaml: Path) -> None:
        """Transport defaults to stdio when not specified in YAML."""
        registry = ToolRegistry.from_yaml(valid_yaml)
        for client in registry._servers.values():
            assert client.config.transport == "stdio"


class TestRegistryTools:
    def test_get_all_tools_empty(self) -> None:
        registry = ToolRegistry()
        assert registry.get_all_tools() == []

    def test_get_tool_definitions_for_llm_format(self) -> None:
        registry = ToolRegistry()

        # Create a mock client with tools
        mock_client = MagicMock()
        mock_client.status = ToolStatus.AVAILABLE
        mock_client.tools = [
            ToolDefinition(
                name="search",
                description="Search the web",
                parameters={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                },
                server_name="search-server",
            ),
        ]
        registry._servers["search-server"] = mock_client
        registry._tool_to_server["search"] = "search-server"

        defs = registry.get_tool_definitions_for_llm()
        assert len(defs) == 1
        assert defs[0]["type"] == "function"
        assert defs[0]["function"]["name"] == "search"
        assert defs[0]["function"]["description"] == "Search the web"
        assert "properties" in defs[0]["function"]["parameters"]

    def test_get_tool_definitions_skips_disabled(self) -> None:
        registry = ToolRegistry()
        mock_client = MagicMock()
        mock_client.status = ToolStatus.AVAILABLE
        mock_client.tools = [
            ToolDefinition(name="t1", description="enabled", enabled=True),
            ToolDefinition(name="t2", description="disabled", enabled=False),
        ]
        registry._servers["s"] = mock_client
        defs = registry.get_tool_definitions_for_llm()
        assert len(defs) == 1
        assert defs[0]["function"]["name"] == "t1"


class TestRegistryExecute:
    async def test_execute_tool_not_found(self) -> None:
        registry = ToolRegistry()
        result = await registry.execute_tool("nonexistent", {})
        assert result.success is False
        assert "not found" in (result.error or "")

    async def test_execute_tool_calls_client(self) -> None:
        registry = ToolRegistry()
        mock_client = MagicMock()
        mock_client.call_tool = AsyncMock(
            return_value=MagicMock(call_id="123", result="ok", success=True, error=None)
        )
        registry._servers["srv"] = mock_client
        registry._tool_to_server["my_tool"] = "srv"

        result = await registry.execute_tool("my_tool", {"arg": "val"})
        mock_client.call_tool.assert_called_once_with("my_tool", {"arg": "val"})
        assert result.success is True


class TestRegistryStatus:
    def test_server_status_empty(self) -> None:
        registry = ToolRegistry()
        assert registry.get_server_status() == {}

    def test_server_count_and_tool_count(self) -> None:
        registry = ToolRegistry()
        assert registry.server_count == 0
        assert registry.tool_count == 0

    async def test_connect_all_and_disconnect_all(self) -> None:
        registry = ToolRegistry()
        mock_client = MagicMock()
        mock_client.connect = AsyncMock(return_value=True)
        mock_client.disconnect = AsyncMock()
        mock_client.tools = [
            ToolDefinition(name="t1", description="tool1", server_name="srv"),
        ]
        registry._servers["srv"] = mock_client

        results = await registry.connect_all()
        assert results == {"srv": True}
        assert registry.tool_count == 1

        await registry.disconnect_all()
        mock_client.disconnect.assert_called_once()
        assert registry.tool_count == 0
