"""Tests for WebSocket endpoint."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

from starlette.testclient import TestClient

from clide.api.schemas import AgentState, WSMessageType
from clide.main import create_app


class TestWebSocket:
    def setup_method(self) -> None:
        self.app = create_app()
        self.client = TestClient(self.app)

    def test_websocket_connect_receives_state(self) -> None:
        with self.client.websocket_connect("/ws") as ws:
            data = ws.receive_json()
            assert data["type"] == WSMessageType.STATE_CHANGE
            payload = data["payload"]
            assert payload["previous_state"] == "idle"
            assert payload["new_state"] == "idle"
            assert payload["reason"] == "connected"

    def test_websocket_chat_message_receives_chunks(self) -> None:
        with self.client.websocket_connect("/ws") as ws:
            # Consume initial state message
            ws.receive_json()

            # Send a chat message
            msg = {
                "type": "chat_message",
                "payload": {"content": "hello", "role": "user"},
            }
            ws.send_text(json.dumps(msg))

            # Should receive at least one chunk with content
            chunk = ws.receive_json()
            assert chunk["type"] == WSMessageType.CHAT_RESPONSE_CHUNK
            assert "content" in chunk["payload"]
            assert chunk["payload"]["done"] is False
            assert len(chunk["payload"]["content"]) > 0

    def test_websocket_chat_message_receives_done(self) -> None:
        with self.client.websocket_connect("/ws") as ws:
            # Consume initial state message
            ws.receive_json()

            msg = {
                "type": "chat_message",
                "payload": {"content": "hello", "role": "user"},
            }
            ws.send_text(json.dumps(msg))

            # Consume content chunks until done
            messages = []
            while True:
                data = ws.receive_json()
                messages.append(data)
                if data["type"] == WSMessageType.CHAT_RESPONSE_CHUNK and data["payload"]["done"]:
                    break

            # Last message should be done=True
            last = messages[-1]
            assert last["type"] == WSMessageType.CHAT_RESPONSE_CHUNK
            assert last["payload"]["done"] is True

    def test_websocket_invalid_json_returns_error(self) -> None:
        with self.client.websocket_connect("/ws") as ws:
            # Consume initial state message
            ws.receive_json()

            ws.send_text("not valid json {{{")

            data = ws.receive_json()
            assert data["type"] == WSMessageType.ERROR
            assert data["payload"]["code"] == "invalid_message"

    def test_websocket_invalid_message_type_returns_error(self) -> None:
        with self.client.websocket_connect("/ws") as ws:
            # Consume initial state message
            ws.receive_json()

            msg = {
                "type": "status",
                "payload": {},
            }
            ws.send_text(json.dumps(msg))

            data = ws.receive_json()
            assert data["type"] == WSMessageType.ERROR
            assert data["payload"]["code"] == "unsupported_type"

    def test_websocket_invalid_payload_returns_error(self) -> None:
        with self.client.websocket_connect("/ws") as ws:
            # Consume initial state message
            ws.receive_json()

            # Send chat_message with invalid payload (missing required fields)
            msg = {
                "type": "chat_message",
                "payload": {"wrong_field": "value"},
            }
            ws.send_text(json.dumps(msg))

            data = ws.receive_json()
            assert data["type"] == WSMessageType.ERROR
            assert data["payload"]["code"] == "invalid_payload"

    def test_websocket_broadcasts_state_after_response(self) -> None:
        """After a chat response completes, a STATE_CHANGE broadcast is sent."""
        with self.client.websocket_connect("/ws") as ws:
            # Consume initial state message
            ws.receive_json()

            msg = {
                "type": "chat_message",
                "payload": {"content": "hello", "role": "user"},
            }
            ws.send_text(json.dumps(msg))

            # Consume all messages until we get the state change
            messages = []
            done_seen = False
            state_seen = False
            while True:
                data = ws.receive_json()
                messages.append(data)
                if data["type"] == WSMessageType.CHAT_RESPONSE_CHUNK and data["payload"]["done"]:
                    done_seen = True
                    continue
                if data["type"] == WSMessageType.STATE_CHANGE:
                    state_seen = True
                    break

            assert done_seen, "Should have received done chunk before state change"
            assert state_seen, "Should have received state change broadcast"

            # Verify the state change payload
            state_msg = messages[-1]
            assert state_msg["payload"]["previous_state"] == "conversing"
            assert state_msg["payload"]["reason"] == "response complete"


class TestLifespanInitialization:
    """Test that the lifespan properly initializes all modules."""

    @patch("clide.main.GoalManager")
    @patch("clide.main.ThinkingScheduler")
    @patch("clide.main.AgentCore")
    @patch("clide.main.AMem")
    @patch("clide.main.Character")
    def test_lifespan_initializes_modules(
        self,
        mock_character_cls: MagicMock,
        mock_amem_cls: MagicMock,
        mock_agent_core_cls: MagicMock,
        mock_scheduler_cls: MagicMock,
        mock_goal_manager: MagicMock,
    ) -> None:
        """Test that lifespan creates and wires all modules."""
        # Set up mock character
        mock_character = MagicMock()
        mock_character.load = AsyncMock()
        mock_character.save = AsyncMock()
        mock_character_cls.return_value = mock_character

        # Set up mock scheduler
        mock_scheduler = MagicMock()
        mock_scheduler.start = AsyncMock()
        mock_scheduler.stop = AsyncMock()
        mock_scheduler_cls.return_value = mock_scheduler

        # Set up mock agent core
        mock_core = MagicMock()

        async def _fake_process(content: str) -> AsyncIterator[str]:
            yield f"Echo: {content}"

        mock_core.process_message = _fake_process
        mock_core.get_state.return_value = AgentState.IDLE
        mock_agent_core_cls.return_value = mock_core

        # Set up mock AMem
        mock_amem = MagicMock()
        mock_amem_cls.return_value = mock_amem

        app = create_app()
        # Use TestClient as context manager to trigger lifespan enter/exit
        with TestClient(app) as client, client.websocket_connect("/ws") as ws:
            data = ws.receive_json()
            assert data["type"] == WSMessageType.STATE_CHANGE

        # Verify modules were initialized
        mock_character_cls.assert_called_once()
        mock_character.load.assert_awaited_once()
        mock_agent_core_cls.assert_called_once()
        mock_amem_cls.assert_called_once()
        mock_scheduler_cls.assert_called_once()
        mock_goal_manager.assert_called_once()

        # Verify scheduler was started (default interval > 0)
        mock_scheduler.set_callback.assert_called_once()
        mock_scheduler.start.assert_awaited_once()

        # Verify shutdown
        mock_scheduler.stop.assert_awaited_once()
        mock_character.save.assert_awaited_once()
