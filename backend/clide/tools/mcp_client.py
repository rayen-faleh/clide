"""MCP client for communicating with tool servers."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import shlex
import uuid
from typing import Any

from clide.tools.models import MCPServerConfig, ToolDefinition, ToolResult, ToolStatus

logger = logging.getLogger(__name__)


class MCPClient:
    """Client for communicating with an MCP server via stdio."""

    def __init__(self, config: MCPServerConfig) -> None:
        self.config = config
        self._process: asyncio.subprocess.Process | None = None
        self._status = ToolStatus.UNAVAILABLE
        self._tools: list[ToolDefinition] = []
        self._request_id = 0
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._reader_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None

    @property
    def status(self) -> ToolStatus:
        """Get current server status."""
        return self._status

    @property
    def tools(self) -> list[ToolDefinition]:
        """Get discovered tools."""
        return self._tools

    async def connect(self) -> bool:
        """Start the MCP server process and discover tools."""
        if not self.config.enabled:
            self._status = ToolStatus.DISABLED
            return False

        try:
            logger.info("Connecting to MCP server: %s", self.config.name)

            cmd_parts = shlex.split(self.config.command)
            full_cmd = cmd_parts + self.config.args

            env = {**os.environ, **self.config.env} if self.config.env else None

            self._process = await asyncio.create_subprocess_exec(
                *full_cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            self._reader_task = asyncio.create_task(self._read_responses())
            self._stderr_task = asyncio.create_task(self._read_stderr())

            # Initialize
            await self._send_request(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "clide", "version": "0.1.0"},
                },
            )

            # Notify initialized
            await self._send_notification("notifications/initialized", {})

            # Discover tools
            result = await self._send_request("tools/list", {})
            if result and "tools" in result:
                self._tools = [
                    ToolDefinition(
                        name=t["name"],
                        description=t.get("description", ""),
                        parameters=t.get("inputSchema", {}),
                        server_name=self.config.name,
                    )
                    for t in result["tools"]
                ]

            self._status = ToolStatus.AVAILABLE
            logger.info(
                "MCP server %s connected: %d tools",
                self.config.name,
                len(self._tools),
            )
            return True

        except Exception as e:
            logger.error("Failed to connect to MCP server %s: %s", self.config.name, e)
            self._status = ToolStatus.ERROR
            # Clean up orphaned subprocess and tasks
            if self._reader_task:
                self._reader_task.cancel()
                self._reader_task = None
            if self._stderr_task:
                self._stderr_task.cancel()
                self._stderr_task = None
            if self._process:
                try:
                    self._process.terminate()
                    await asyncio.wait_for(self._process.wait(), timeout=5.0)
                except (TimeoutError, ProcessLookupError):
                    self._process.kill()
                self._process = None
            for future in self._pending.values():
                if not future.done():
                    future.cancel()
            self._pending.clear()
            return False

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        """Execute a tool call on the MCP server."""
        call_id = str(uuid.uuid4())

        if self._status != ToolStatus.AVAILABLE:
            return ToolResult(
                call_id=call_id,
                error=f"Server {self.config.name} is not available (status: {self._status})",
                success=False,
            )

        try:
            result = await self._send_request(
                "tools/call",
                {
                    "name": tool_name,
                    "arguments": arguments,
                },
            )

            if result and "content" in result:
                # Extract text content from MCP response
                content_parts = result["content"]
                text_parts = [
                    p["text"]
                    for p in content_parts
                    if isinstance(p, dict) and p.get("type") == "text"
                ]
                return ToolResult(
                    call_id=call_id,
                    result="\n".join(text_parts) if text_parts else result,
                    success=not result.get("isError", False),
                )

            return ToolResult(call_id=call_id, result=result, success=True)

        except Exception as e:
            return ToolResult(
                call_id=call_id,
                error=str(e),
                success=False,
            )

    async def disconnect(self) -> None:
        """Stop the MCP server process."""
        if self._reader_task:
            self._reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader_task

        if self._stderr_task:
            self._stderr_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._stderr_task

        if self._process:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except TimeoutError:
                self._process.kill()
            self._process = None

        # Cancel any pending futures
        for future in self._pending.values():
            if not future.done():
                future.cancel()
        self._pending.clear()

        self._status = ToolStatus.UNAVAILABLE
        self._tools = []
        logger.info("MCP server %s disconnected", self.config.name)

    async def _send_request(self, method: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """Send a JSON-RPC request and wait for response."""
        if not self._process or not self._process.stdin:
            return None

        self._request_id += 1
        request_id = self._request_id

        message = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }

        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future

        data = json.dumps(message) + "\n"
        self._process.stdin.write(data.encode())
        await self._process.stdin.drain()

        try:
            return await asyncio.wait_for(future, timeout=30.0)
        except TimeoutError:
            self._pending.pop(request_id, None)
            return None

    async def _send_notification(self, method: str, params: dict[str, Any]) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        if not self._process or not self._process.stdin:
            return

        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }

        data = json.dumps(message) + "\n"
        self._process.stdin.write(data.encode())
        await self._process.stdin.drain()

    async def _read_responses(self) -> None:
        """Background task to read responses from the server."""
        if not self._process or not self._process.stdout:
            return

        while True:
            try:
                line = await self._process.stdout.readline()
                if not line:
                    break

                data = json.loads(line.decode().strip())
                request_id = data.get("id")

                if request_id and request_id in self._pending:
                    future = self._pending.pop(request_id)
                    if "error" in data:
                        future.set_exception(Exception(str(data["error"])))
                    else:
                        future.set_result(data.get("result", {}))

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug("Error reading MCP response: %s", e)

        # Reader exited — subprocess likely died
        if self._status == ToolStatus.AVAILABLE:
            self._status = ToolStatus.ERROR
            logger.warning("MCP server %s: reader exited, marking as ERROR", self.config.name)
        for future in self._pending.values():
            if not future.done():
                future.cancel()
        self._pending.clear()

    async def _read_stderr(self) -> None:
        """Read stderr to prevent buffer deadlock."""
        if not self._process or not self._process.stderr:
            return
        while True:
            try:
                line = await self._process.stderr.readline()
                if not line:
                    break
                logger.debug(
                    "MCP server %s stderr: %s",
                    self.config.name,
                    line.decode().strip(),
                )
            except asyncio.CancelledError:
                break
            except Exception:
                break
