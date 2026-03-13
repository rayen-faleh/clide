"""Tests for tool data models."""

from __future__ import annotations

from clide.tools.models import (
    MCPServerConfig,
    ToolCall,
    ToolDefinition,
    ToolResult,
    ToolStatus,
)


class TestToolStatus:
    def test_tool_status_values(self) -> None:
        assert ToolStatus.AVAILABLE.value == "available"
        assert ToolStatus.UNAVAILABLE.value == "unavailable"
        assert ToolStatus.ERROR.value == "error"
        assert ToolStatus.DISABLED.value == "disabled"


class TestToolDefinition:
    def test_defaults(self) -> None:
        td = ToolDefinition(name="test", description="A test tool")
        assert td.name == "test"
        assert td.description == "A test tool"
        assert td.parameters == {}
        assert td.server_name == ""
        assert td.enabled is True

    def test_with_params(self) -> None:
        params = {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        }
        td = ToolDefinition(
            name="search",
            description="Search tool",
            parameters=params,
            server_name="search-server",
            enabled=False,
        )
        assert td.parameters == params
        assert td.server_name == "search-server"
        assert td.enabled is False


class TestToolCall:
    def test_creation(self) -> None:
        tc = ToolCall(tool_name="search", arguments={"query": "hello"}, call_id="abc-123")
        assert tc.tool_name == "search"
        assert tc.arguments == {"query": "hello"}
        assert tc.call_id == "abc-123"

    def test_defaults(self) -> None:
        tc = ToolCall(tool_name="test")
        assert tc.arguments == {}
        assert tc.call_id == ""


class TestToolResult:
    def test_success(self) -> None:
        tr = ToolResult(call_id="abc", result="some data", success=True)
        assert tr.call_id == "abc"
        assert tr.result == "some data"
        assert tr.error is None
        assert tr.success is True

    def test_error(self) -> None:
        tr = ToolResult(call_id="abc", error="something broke", success=False)
        assert tr.call_id == "abc"
        assert tr.result is None
        assert tr.error == "something broke"
        assert tr.success is False


class TestMCPServerConfig:
    def test_defaults(self) -> None:
        cfg = MCPServerConfig(name="test", command="python -m test")
        assert cfg.name == "test"
        assert cfg.command == "python -m test"
        assert cfg.args == []
        assert cfg.env == {}
        assert cfg.enabled is True
        assert cfg.description == ""

    def test_full_config(self) -> None:
        cfg = MCPServerConfig(
            name="search",
            command="node",
            args=["search-server.js"],
            env={"API_KEY": "secret"},
            enabled=False,
            description="Search server",
        )
        assert cfg.args == ["search-server.js"]
        assert cfg.env == {"API_KEY": "secret"}
        assert cfg.enabled is False
        assert cfg.description == "Search server"
