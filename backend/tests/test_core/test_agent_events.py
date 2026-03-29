"""Tests for agent event models."""

from __future__ import annotations

from clide.core.agent_events import (
    AgentStepEvent,
    CheckpointEvent,
    LLMCallEvent,
    StateChangeEvent,
    TextChunkEvent,
    ToolCallEvent,
    ToolResultEvent,
)


class TestTextChunkEvent:
    def test_defaults_done_false(self) -> None:
        e = TextChunkEvent(content="hello")
        assert e.content == "hello"
        assert e.done is False

    def test_done_true(self) -> None:
        e = TextChunkEvent(content="final", done=True)
        assert e.done is True


class TestToolCallEvent:
    def test_creation(self) -> None:
        e = ToolCallEvent(tool_name="search", arguments={"q": "test"}, call_id="abc123")
        assert e.tool_name == "search"
        assert e.arguments == {"q": "test"}
        assert e.call_id == "abc123"


class TestToolResultEvent:
    def test_defaults(self) -> None:
        e = ToolResultEvent(call_id="abc123", result={"data": 1})
        assert e.success is True
        assert e.error is None

    def test_failure(self) -> None:
        e = ToolResultEvent(call_id="abc123", result=None, error="timeout", success=False)
        assert e.success is False
        assert e.error == "timeout"


class TestCheckpointEvent:
    def test_creation(self) -> None:
        e = CheckpointEvent(content="Phase 1 summary", phase=1, total_phases=3)
        assert e.phase == 1
        assert e.total_phases == 3


class TestStateChangeEvent:
    def test_defaults(self) -> None:
        e = StateChangeEvent(previous_state="idle", new_state="working")
        assert e.reason == ""

    def test_with_reason(self) -> None:
        e = StateChangeEvent(previous_state="idle", new_state="thinking", reason="scheduled")
        assert e.reason == "scheduled"


class TestLLMCallEvent:
    def test_defaults(self) -> None:
        e = LLMCallEvent(model="claude-sonnet-4-6")
        assert e.prompt_tokens == 0
        assert e.completion_tokens == 0
        assert e.purpose == "tool_loop"

    def test_with_usage(self) -> None:
        e = LLMCallEvent(model="gpt-4", prompt_tokens=100, completion_tokens=50, purpose="chat")
        assert e.prompt_tokens == 100
        assert e.purpose == "chat"


class TestAgentStepEventDispatch:
    """Verify isinstance dispatch works for all union variants."""

    def test_text_chunk_is_agent_step_event(self) -> None:
        e: AgentStepEvent = TextChunkEvent(content="hi")
        assert isinstance(e, TextChunkEvent)

    def test_tool_call_is_agent_step_event(self) -> None:
        e: AgentStepEvent = ToolCallEvent(tool_name="t", arguments={}, call_id="x")
        assert isinstance(e, ToolCallEvent)

    def test_tool_result_is_agent_step_event(self) -> None:
        e: AgentStepEvent = ToolResultEvent(call_id="x", result=None)
        assert isinstance(e, ToolResultEvent)

    def test_checkpoint_is_agent_step_event(self) -> None:
        e: AgentStepEvent = CheckpointEvent(content="c", phase=1, total_phases=1)
        assert isinstance(e, CheckpointEvent)

    def test_state_change_is_agent_step_event(self) -> None:
        e: AgentStepEvent = StateChangeEvent(previous_state="a", new_state="b")
        assert isinstance(e, StateChangeEvent)

    def test_llm_call_is_agent_step_event(self) -> None:
        e: AgentStepEvent = LLMCallEvent(model="m")
        assert isinstance(e, LLMCallEvent)

    def test_dispatch_all_types(self) -> None:
        events: list[AgentStepEvent] = [
            TextChunkEvent(content="a"),
            ToolCallEvent(tool_name="t", arguments={}, call_id="1"),
            ToolResultEvent(call_id="1", result="ok"),
            CheckpointEvent(content="c", phase=1, total_phases=1),
            StateChangeEvent(previous_state="x", new_state="y"),
            LLMCallEvent(model="m"),
        ]
        types_seen = set()
        for event in events:
            match event:
                case TextChunkEvent():
                    types_seen.add("text")
                case ToolCallEvent():
                    types_seen.add("tool_call")
                case ToolResultEvent():
                    types_seen.add("tool_result")
                case CheckpointEvent():
                    types_seen.add("checkpoint")
                case StateChangeEvent():
                    types_seen.add("state_change")
                case LLMCallEvent():
                    types_seen.add("llm_call")
        assert types_seen == {"text", "tool_call", "tool_result", "checkpoint", "state_change", "llm_call"}
