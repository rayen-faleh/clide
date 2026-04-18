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

    def test_stderr_task_initially_none(self, enabled_config: MCPServerConfig) -> None:
        client = MCPClient(enabled_config)
        assert client._stderr_task is None


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

    async def test_connect_uses_shlex_split(self) -> None:
        """Verify that shlex.split is used to parse the command string."""
        config = MCPServerConfig(
            name="shlex-test",
            command='python -m "my module"',
            args=["--flag"],
        )
        client = MCPClient(config)

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.side_effect = OSError("intentional")
            await client.connect()

            # shlex.split('python -m "my module"') -> ["python", "-m", "my module"]
            # + args ["--flag"] -> ["python", "-m", "my module", "--flag"]
            mock_exec.assert_called_once()
            call_args = mock_exec.call_args[0]
            assert call_args == ("python", "-m", "my module", "--flag")


class TestMCPClientCallTool:
    async def test_call_tool_when_unavailable(self, enabled_config: MCPServerConfig) -> None:
        client = MCPClient(enabled_config)
        result = await client.call_tool("some_tool", {"arg": "val"})
        assert result.success is False
        assert "not available" in (result.error or "")

    async def test_call_tool_timeout_returns_failure(self, enabled_config: MCPServerConfig) -> None:
        """Fix 1: timeout (None from _send_request) must return success=False, not success=True."""
        client = MCPClient(enabled_config)
        client._status = ToolStatus.AVAILABLE

        with patch.object(client, "_send_request", new_callable=AsyncMock, return_value=None):
            result = await client.call_tool("slow_tool", {})

        assert result.success is False
        assert result.error is not None
        assert "timed out" in result.error.lower()

    async def test_call_tool_is_error_populates_error_field(self, enabled_config: MCPServerConfig) -> None:
        """Fix 4: isError=true must set success=False AND populate error with the content text."""
        client = MCPClient(enabled_config)
        client._status = ToolStatus.AVAILABLE

        mcp_response = {
            "content": [{"type": "text", "text": "File not found: /tmp/missing.txt"}],
            "isError": True,
        }
        with patch.object(client, "_send_request", new_callable=AsyncMock, return_value=mcp_response):
            result = await client.call_tool("read_file", {"path": "/tmp/missing.txt"})

        assert result.success is False
        assert result.error == "File not found: /tmp/missing.txt"

    async def test_call_tool_success_extracts_text_content(self, enabled_config: MCPServerConfig) -> None:
        """Normal success path still works after refactor."""
        client = MCPClient(enabled_config)
        client._status = ToolStatus.AVAILABLE

        mcp_response = {
            "content": [{"type": "text", "text": "search result here"}],
            "isError": False,
        }
        with patch.object(client, "_send_request", new_callable=AsyncMock, return_value=mcp_response):
            result = await client.call_tool("search", {"q": "test"})

        assert result.success is True
        assert result.result == "search result here"
        assert result.error is None


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

        # Create real cancelled tasks to simulate reader_task and stderr_task
        async def noop() -> None:
            await asyncio.sleep(100)

        reader_task = asyncio.create_task(noop())
        reader_task.cancel()
        client._reader_task = reader_task

        stderr_task = asyncio.create_task(noop())
        stderr_task.cancel()
        client._stderr_task = stderr_task

        await client.disconnect()

        assert client.status == ToolStatus.UNAVAILABLE
        assert client.tools == []
        assert client._process is None
        mock_process.terminate.assert_called_once()

    async def test_disconnect_cancels_stderr_task(self, enabled_config: MCPServerConfig) -> None:
        client = MCPClient(enabled_config)

        async def noop() -> None:
            await asyncio.sleep(100)

        stderr_task = asyncio.create_task(noop())
        client._stderr_task = stderr_task

        mock_process = MagicMock()
        mock_process.terminate = MagicMock()
        mock_process.kill = MagicMock()
        mock_process.wait = AsyncMock(return_value=0)
        client._process = mock_process

        await client.disconnect()
        assert stderr_task.cancelled()
