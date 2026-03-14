"""Tool registry - manages MCP server connections and tool discovery."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from clide.config.settings import _PROJECT_ROOT
from clide.tools.mcp_client import MCPClient
from clide.tools.models import MCPServerConfig, ToolDefinition, ToolResult, ToolStatus

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Registry of available tools from MCP servers."""

    def __init__(self) -> None:
        self._servers: dict[str, MCPClient] = {}
        self._tool_to_server: dict[str, str] = {}  # tool_name -> server_name

    @classmethod
    def from_yaml(cls, path: str | Path | None = None) -> ToolRegistry:
        """Load tool configuration from YAML."""
        registry = cls()
        resolved = Path(path) if path is not None else _PROJECT_ROOT / "config" / "tools.yaml"

        if not resolved.exists():
            logger.warning("Tools config not found: %s", resolved)
            return registry

        with open(resolved) as f:
            data = yaml.safe_load(f) or {}

        tools_config = data.get("tools", [])
        if not isinstance(tools_config, list):
            return registry

        for tool_conf in tools_config:
            if not isinstance(tool_conf, dict):
                continue
            config = MCPServerConfig(
                name=tool_conf.get("name", ""),
                command=tool_conf.get("command", ""),
                transport=tool_conf.get("transport", "stdio"),
                args=tool_conf.get("args", []),
                env=tool_conf.get("env", {}),
                enabled=tool_conf.get("enabled", True),
                description=tool_conf.get("description", ""),
            )
            if config.name and config.command:
                registry._servers[config.name] = MCPClient(config)

        return registry

    async def connect_all(self) -> dict[str, bool]:
        """Connect to all configured MCP servers."""
        results: dict[str, bool] = {}
        for name, client in self._servers.items():
            success = await client.connect()
            results[name] = success

            if success:
                for tool in client.tools:
                    self._tool_to_server[tool.name] = name

        return results

    async def disconnect_all(self) -> None:
        """Disconnect from all MCP servers."""
        for client in self._servers.values():
            await client.disconnect()
        self._tool_to_server.clear()

    def get_all_tools(self) -> list[ToolDefinition]:
        """Get all available tool definitions across all servers."""
        tools: list[ToolDefinition] = []
        for client in self._servers.values():
            if client.status == ToolStatus.AVAILABLE:
                tools.extend(client.tools)
        return tools

    def get_tool_definitions_for_llm(self) -> list[dict[str, Any]]:
        """Get tool definitions formatted for LLM function calling.

        Returns tools in the format expected by litellm/anthropic/openai.
        """
        definitions: list[dict[str, Any]] = []
        for tool in self.get_all_tools():
            if not tool.enabled:
                continue
            definitions.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters or {"type": "object", "properties": {}},
                    },
                }
            )
        return definitions

    async def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        """Execute a tool by name."""
        server_name = self._tool_to_server.get(tool_name)
        if not server_name:
            return ToolResult(
                call_id="",
                error=f"Tool '{tool_name}' not found in any connected server",
                success=False,
            )

        client = self._servers.get(server_name)
        if not client:
            return ToolResult(
                call_id="",
                error=f"Server '{server_name}' not found",
                success=False,
            )

        return await client.call_tool(tool_name, arguments)

    def get_server_status(self) -> dict[str, str]:
        """Get status of all configured servers."""
        return {name: client.status.value for name, client in self._servers.items()}

    @property
    def server_count(self) -> int:
        """Number of configured servers."""
        return len(self._servers)

    @property
    def tool_count(self) -> int:
        """Number of discovered tools."""
        return len(self._tool_to_server)
