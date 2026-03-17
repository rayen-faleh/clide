"""Tests for WebSocket message schemas."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from clide.api.schemas import (
    AgentState,
    ChatMessagePayload,
    ChatResponseChunkPayload,
    ErrorPayload,
    MoodPayload,
    StateChangePayload,
    ThoughtPayload,
    ToolCallPayload,
    ToolResultPayload,
    WSMessage,
    WSMessageType,
)


class TestWSMessageType:
    def test_all_message_types_are_strings(self) -> None:
        for msg_type in WSMessageType:
            assert isinstance(msg_type.value, str)

    def test_expected_message_types_exist(self) -> None:
        expected = {
            "chat_message",
            "chat_response",
            "chat_response_chunk",
            "thought",
            "mood_update",
            "memory_update",
            "tool_call",
            "tool_result",
            "tool_checkpoint",
            "state_change",
            "status",
            "error",
        }
        actual = {t.value for t in WSMessageType}
        assert actual == expected


class TestAgentState:
    def test_all_states_are_strings(self) -> None:
        for state in AgentState:
            assert isinstance(state.value, str)

    def test_expected_states_exist(self) -> None:
        expected = {"sleeping", "idle", "thinking", "conversing", "working"}
        actual = {s.value for s in AgentState}
        assert actual == expected


class TestWSMessage:
    def test_create_with_defaults(self) -> None:
        msg = WSMessage(type=WSMessageType.STATUS)
        assert msg.type == WSMessageType.STATUS
        assert msg.payload == {}
        assert isinstance(msg.timestamp, datetime)

    def test_create_with_payload(self) -> None:
        msg = WSMessage(
            type=WSMessageType.CHAT_MESSAGE,
            payload={"content": "hello", "role": "user"},
        )
        assert msg.payload["content"] == "hello"

    def test_json_round_trip(self) -> None:
        msg = WSMessage(
            type=WSMessageType.CHAT_MESSAGE,
            payload={"content": "test"},
        )
        json_str = msg.model_dump_json()
        restored = WSMessage.model_validate_json(json_str)
        assert restored.type == msg.type
        assert restored.payload == msg.payload


class TestChatMessagePayload:
    def test_user_role(self) -> None:
        payload = ChatMessagePayload(content="hello", role="user")
        assert payload.role == "user"

    def test_assistant_role(self) -> None:
        payload = ChatMessagePayload(content="hi there", role="assistant")
        assert payload.role == "assistant"

    def test_invalid_role_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ChatMessagePayload(content="hello", role="system")  # type: ignore[arg-type]

    def test_json_round_trip(self) -> None:
        payload = ChatMessagePayload(content="test", role="user")
        restored = ChatMessagePayload.model_validate_json(payload.model_dump_json())
        assert restored == payload


class TestChatResponseChunkPayload:
    def test_defaults(self) -> None:
        chunk = ChatResponseChunkPayload(content="hello")
        assert chunk.done is False

    def test_done_flag(self) -> None:
        chunk = ChatResponseChunkPayload(content="", done=True)
        assert chunk.done is True


class TestMoodPayload:
    def test_valid_mood(self) -> None:
        mood = MoodPayload(mood="curious", intensity=0.8, reason="exploring")
        assert mood.intensity == 0.8

    def test_intensity_at_bounds(self) -> None:
        MoodPayload(mood="calm", intensity=0.0)
        MoodPayload(mood="excited", intensity=1.0)

    def test_intensity_below_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MoodPayload(mood="sad", intensity=-0.1)

    def test_intensity_above_one_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MoodPayload(mood="manic", intensity=1.1)

    def test_default_reason(self) -> None:
        mood = MoodPayload(mood="calm", intensity=0.5)
        assert mood.reason == ""


class TestStateChangePayload:
    def test_valid_transition(self) -> None:
        change = StateChangePayload(
            previous_state=AgentState.IDLE,
            new_state=AgentState.CONVERSING,
            reason="user message received",
        )
        assert change.previous_state == AgentState.IDLE
        assert change.new_state == AgentState.CONVERSING

    def test_default_reason(self) -> None:
        change = StateChangePayload(
            previous_state=AgentState.IDLE,
            new_state=AgentState.THINKING,
        )
        assert change.reason == ""


class TestThoughtPayload:
    def test_autonomous_thought(self) -> None:
        thought = ThoughtPayload(content="I wonder about...", source="autonomous")
        assert thought.source == "autonomous"

    def test_reactive_thought(self) -> None:
        thought = ThoughtPayload(content="Reflecting on...", source="reactive")
        assert thought.source == "reactive"

    def test_invalid_source_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ThoughtPayload(content="test", source="random")  # type: ignore[arg-type]


class TestToolCallPayload:
    def test_create(self) -> None:
        call = ToolCallPayload(
            tool_name="web_search",
            arguments={"query": "test"},
            call_id="abc123",
        )
        assert call.tool_name == "web_search"

    def test_defaults(self) -> None:
        call = ToolCallPayload(tool_name="test")
        assert call.arguments == {}
        assert call.call_id == ""


class TestToolResultPayload:
    def test_success(self) -> None:
        result = ToolResultPayload(call_id="abc", result={"data": "value"})
        assert result.error is None

    def test_error(self) -> None:
        result = ToolResultPayload(call_id="abc", error="Something failed")
        assert result.error == "Something failed"


class TestErrorPayload:
    def test_create(self) -> None:
        error = ErrorPayload(message="Something went wrong")
        assert error.code == "unknown"

    def test_with_code(self) -> None:
        error = ErrorPayload(message="Not found", code="not_found")
        assert error.code == "not_found"
