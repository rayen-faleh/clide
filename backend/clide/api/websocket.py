"""WebSocket endpoint for agent communication."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from clide.api.schemas import (
    AgentState,
    ChatMessagePayload,
    ChatResponseChunkPayload,
    ErrorPayload,
    StateChangePayload,
    ToolCallPayload,
    ToolCheckpointPayload,
    ToolResultPayload,
    WSMessage,
    WSMessageType,
)

logger = logging.getLogger(__name__)

ws_router = APIRouter()


@runtime_checkable
class AgentCoreProtocol(Protocol):
    """Protocol that the agent core must implement."""

    def process_message(self, content: str) -> AsyncIterator[str]:
        """Process a user message and yield response chunks."""
        ...

    def get_state(self) -> AgentState:
        """Get current agent state."""
        ...


class StubAgentCore:
    """Stub agent core for development/testing before real core is available."""

    def get_state(self) -> AgentState:
        return AgentState.IDLE

    async def process_message(self, content: str) -> AsyncIterator[str]:
        yield f"Echo: {content}"


# Global agent core instance — will be replaced by real core after Phase 1 merge
_agent_core: AgentCoreProtocol = StubAgentCore()


def set_agent_core(core: AgentCoreProtocol) -> None:
    """Set the global agent core instance."""
    global _agent_core  # noqa: PLW0603
    _agent_core = core


def get_agent_core() -> AgentCoreProtocol:
    """Get the global agent core instance."""
    return _agent_core


class ConnectionManager:
    """Manage active WebSocket connections."""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("WebSocket client connected (%d total)", len(self.active_connections))

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info("Client disconnected (%d remaining)", len(self.active_connections))

    async def send_message(self, websocket: WebSocket, message: WSMessage) -> None:
        try:
            await websocket.send_json(message.model_dump(mode="json"))
        except Exception:
            logger.debug("Failed to send message to client, connection may be closed")

    async def broadcast(self, message: WSMessage) -> None:
        dead: list[WebSocket] = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message.model_dump(mode="json"))
            except Exception:
                dead.append(connection)
        for connection in dead:
            self.active_connections.remove(connection)


manager = ConnectionManager()


ALLOWED_ORIGINS = {
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
}


@ws_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Main WebSocket endpoint for agent communication."""
    # Validate origin to prevent cross-site WebSocket hijacking (ClawJacked-style)
    origin = websocket.headers.get("origin", "")
    if origin and origin not in ALLOWED_ORIGINS:
        logger.warning("WebSocket connection rejected: unauthorized origin '%s'", origin)
        await websocket.close(code=4003, reason="Unauthorized origin")
        return

    await manager.connect(websocket)
    core = get_agent_core()

    # Send initial state
    await manager.send_message(
        websocket,
        WSMessage(
            type=WSMessageType.STATE_CHANGE,
            payload=StateChangePayload(
                previous_state=AgentState.IDLE,
                new_state=AgentState.IDLE,
                reason="connected",
            ).model_dump(),
        ),
    )

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
                msg = WSMessage.model_validate(data)
            except (json.JSONDecodeError, Exception) as e:
                await manager.send_message(
                    websocket,
                    WSMessage(
                        type=WSMessageType.ERROR,
                        payload=ErrorPayload(
                            message=f"Invalid message: {e}",
                            code="invalid_message",
                        ).model_dump(),
                    ),
                )
                continue

            logger.debug("Received WS message: type=%s", msg.type.value)

            if msg.type == WSMessageType.CHAT_MESSAGE:
                await _handle_chat_message(websocket, msg, core)
            else:
                await manager.send_message(
                    websocket,
                    WSMessage(
                        type=WSMessageType.ERROR,
                        payload=ErrorPayload(
                            message=f"Unsupported message type: {msg.type}",
                            code="unsupported_type",
                        ).model_dump(),
                    ),
                )

    except WebSocketDisconnect:
        logger.info("Client disconnected")
    finally:
        manager.disconnect(websocket)


async def _handle_chat_message(
    websocket: WebSocket,
    msg: WSMessage,
    core: AgentCoreProtocol,
) -> None:
    """Handle an incoming chat message."""
    try:
        payload = ChatMessagePayload.model_validate(msg.payload)
    except Exception:
        await manager.send_message(
            websocket,
            WSMessage(
                type=WSMessageType.ERROR,
                payload=ErrorPayload(
                    message="Invalid chat message payload",
                    code="invalid_payload",
                ).model_dump(),
            ),
        )
        return

    # Set tool event callback to broadcast to all clients
    async def tool_event_handler(event: dict[str, Any]) -> None:
        """Broadcast tool call, result, and checkpoint events."""
        # Handle checkpoint events from phased tool execution
        if event.get("checkpoint"):
            await manager.broadcast(
                WSMessage(
                    type=WSMessageType.TOOL_CHECKPOINT,
                    payload=ToolCheckpointPayload(
                        content=event.get("content", ""),
                        phase=event.get("phase", 0),
                        total_phases=event.get("total_phases", 3),
                    ).model_dump(),
                )
            )
            return

        # Broadcast tool call
        await manager.broadcast(
            WSMessage(
                type=WSMessageType.TOOL_CALL,
                payload=ToolCallPayload(
                    tool_name=event.get("tool_name", ""),
                    arguments=event.get("arguments", {}),
                    call_id=event.get("call_id", ""),
                ).model_dump(),
            )
        )
        # Broadcast tool result
        await manager.broadcast(
            WSMessage(
                type=WSMessageType.TOOL_RESULT,
                payload=ToolResultPayload(
                    call_id=event.get("call_id", ""),
                    result=event.get("result"),
                    error=event.get("error"),
                ).model_dump(),
            )
        )

    if hasattr(core, "set_tool_event_callback"):
        core.set_tool_event_callback(tool_event_handler)

    # Stream response chunks
    try:
        logger.info("Streaming response to client...")
        async for chunk in core.process_message(payload.content):
            await manager.send_message(
                websocket,
                WSMessage(
                    type=WSMessageType.CHAT_RESPONSE_CHUNK,
                    payload=ChatResponseChunkPayload(
                        content=chunk,
                        done=False,
                    ).model_dump(),
                ),
            )

        # Send final done message
        logger.info("Response stream complete (done=True sent)")
        await manager.send_message(
            websocket,
            WSMessage(
                type=WSMessageType.CHAT_RESPONSE_CHUNK,
                payload=ChatResponseChunkPayload(
                    content="",
                    done=True,
                ).model_dump(),
            ),
        )

        # Broadcast state change to all clients
        new_state = core.get_state()
        logger.debug(
            "Broadcasting state change: %s -> %s",
            AgentState.CONVERSING.value,
            new_state.value,
        )
        await manager.broadcast(
            WSMessage(
                type=WSMessageType.STATE_CHANGE,
                payload=StateChangePayload(
                    previous_state=AgentState.CONVERSING,
                    new_state=core.get_state(),
                    reason="response complete",
                ).model_dump(),
            )
        )
    except Exception as e:
        logger.exception("Error handling chat message: %s", e)
        await manager.send_message(
            websocket,
            WSMessage(
                type=WSMessageType.ERROR,
                payload=ErrorPayload(
                    message=f"Processing error: {e}",
                    code="processing_error",
                ).model_dump(),
            ),
        )
