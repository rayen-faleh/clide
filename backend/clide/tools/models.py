"""Tool-related data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ToolStatus(StrEnum):
    """Status of a tool/MCP server."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    ERROR = "error"
    DISABLED = "disabled"


@dataclass
class ToolDefinition:
    """A tool that can be called by the agent."""

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)  # JSON Schema
    server_name: str = ""  # Which MCP server provides this tool
    enabled: bool = True


@dataclass
class ToolCall:
    """A request to execute a tool."""

    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    call_id: str = ""


@dataclass
class ToolResult:
    """Result from executing a tool."""

    call_id: str
    result: Any = None
    error: str | None = None
    success: bool = True


@dataclass
class MCPServerConfig:
    """Configuration for an MCP server."""

    name: str
    command: str  # e.g., "python -m clide.tools.web_search"
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    description: str = ""
