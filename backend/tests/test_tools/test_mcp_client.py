"""Tests for MCP client."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clide.tools.mcp_client import MCPClient
from clide.tools.models import MCPServerConfig, ToolStatus


@pytest.fixture
def disabled_config() -> MCPServerConfig:
    return MCPServerConfig(name="disabled", command="echo", enabled=False)


@pytest.fixture
def enabled_config() -> MCPServerConfig:
    return MCPServerConfig(name="test-server", command="python", args=["-m", "test_server"])


class TestMCPClientInit:
    def test_initial_status_unavailable(self, enabled_config: MCPServerConfig) -> None:
        client = MCPClient(enabled_config)
        assert client.status == ToolStatus.UNAVAILABLE

    def test_tools_empty_initially(self, enabled_config: MCPServerConfig) -> None:
        client = MCPClient(enabled_config)
        assert client.tools == []


class TestMCPClientConnect:
    async def test_connect_disabled_server(self, disabled_config: MCPServerConfig) -> None:
        client = MCPClient(disabled_config)
        result = await client.connect()
        assert result is False
        assert client.status == ToolStatus.DISABLED

    async def test_connect_failure_sets_error_status(self, enabled_config: MCPServerConfig) -> None:
        client = MCPClient(enabled_config)
        with patch("asyncio.create_subprocess_exec", side_effect=OSError("not found")):
            result = await client.connect()
        assert result is False
        assert client.status == ToolStatus.ERROR


class TestMCPClientCallTool:
    async def test_call_tool_when_unavailable(self, enabled_config: MCPServerConfig) -> None:
        client = MCPClient(enabled_config)
        result = await client.call_tool("some_tool", {"arg": "val"})
        assert result.success is False
        assert "not available" in (result.error or "")


class TestMCPClientDisconnect:
    async def test_disconnect_cleans_up(self, enabled_config: MCPServerConfig) -> None:
        client = MCPClient(enabled_config)

        # Simulate a connected state
        mock_process = MagicMock()
        mock_process.terminate = MagicMock()
        mock_process.kill = MagicMock()
        mock_process.wait = AsyncMock(return_value=0)
        client._process = mock_process
        client._status = ToolStatus.AVAILABLE

        # Create a real cancelled task to simulate reader_task
        async def noop() -> None:
            await asyncio.sleep(100)

        real_task = asyncio.create_task(noop())
        real_task.cancel()
        client._reader_task = real_task

        await client.disconnect()

        assert client.status == ToolStatus.UNAVAILABLE
        assert client.tools == []
        assert client._process is None
        mock_process.terminate.assert_called_once()
