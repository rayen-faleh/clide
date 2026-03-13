"""Tests for WebSocket endpoint."""

from __future__ import annotations

import json

from starlette.testclient import TestClient

from clide.api.schemas import WSMessageType
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
