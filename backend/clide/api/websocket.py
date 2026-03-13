"""WebSocket endpoint for agent communication."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from clide.api.schemas import (
    AgentState,
    ChatMessagePayload,
    ChatResponseChunkPayload,
    ErrorPayload,
    StateChangePayload,
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

    def disconnect(self, websocket: WebSocket) -> None:
        self.active_connections.remove(websocket)

    async def send_message(self, websocket: WebSocket, message: WSMessage) -> None:
        await websocket.send_json(message.model_dump(mode="json"))

    async def broadcast(self, message: WSMessage) -> None:
        for connection in self.active_connections:
            await connection.send_json(message.model_dump(mode="json"))


manager = ConnectionManager()


@ws_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Main WebSocket endpoint for agent communication."""
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
        manager.disconnect(websocket)
        logger.info("Client disconnected")


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

    # Stream response chunks
    try:
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
        logger.exception("Error processing message")
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
