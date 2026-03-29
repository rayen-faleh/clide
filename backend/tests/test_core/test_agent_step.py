"""Tests for AgentCore.agent_step() unified loop."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clide.api.schemas import AgentState
from clide.core.agent import AgentCore
from clide.core.agent_events import (
    CheckpointEvent,
    LLMCallEvent,
    StateChangeEvent,
    TextChunkEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from clide.core.event_log import EventLog
from clide.tools.models import ToolResult


# Helper to collect all events from agent_step
async def collect_events(agent_step_iter: Any) -> list[Any]:
    events = []
    async for event in agent_step_iter:
        events.append(event)
    return events


# Helper to make a mock LLM response with tool calls
def make_tool_response(tool_calls: list[tuple[str, dict[str, Any], str]]) -> MagicMock:
    """Make a mock litellm response with tool_calls."""
    mock_tool_calls = []
    for name, args, cid in tool_calls:
        tc = MagicMock()
        tc.function.name = name
        tc.function.arguments = json.dumps(args)
        tc.id = cid
        mock_tool_calls.append(tc)

    choice = MagicMock()
    choice.finish_reason = "tool_calls"
    choice.message.tool_calls = mock_tool_calls
    choice.message.content = None
    choice.message.model_dump.return_value = {
        "role": "assistant",
        "tool_calls": [
            {
                "id": tc.id,
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in mock_tool_calls
        ],
    }

    response = MagicMock()
    response.choices = [choice]
    response.usage = MagicMock(prompt_tokens=100, completion_tokens=50)
    return response


# Helper to make a mock LLM response with text
def make_text_response(text: str) -> MagicMock:
    choice = MagicMock()
    choice.finish_reason = "stop"
    choice.message.tool_calls = None
    choice.message.content = text

    response = MagicMock()
    response.choices = [choice]
    response.usage = MagicMock(prompt_tokens=100, completion_tokens=50)
    return response


class TestAgentStepNoTools:
    """Tests for the streaming (no-tools) path."""

    @pytest.mark.asyncio
    async def test_yields_text_chunks(self) -> None:
        agent = AgentCore()
        agent.state_machine.transition(AgentState.CONVERSING)

        async def fake_stream(messages: Any, config: Any, **kwargs: Any):  # type: ignore[return]
            for chunk in ["Hello", " world", "!"]:
                yield chunk

        with patch("clide.core.agent.stream_completion", side_effect=fake_stream):
            events = await collect_events(
                agent.agent_step(
                    messages=[{"role": "user", "content": "hi"}],
                    tools=[],
                    session_id="test-session",
                    mode="chat",
                )
            )

        text_events = [e for e in events if isinstance(e, TextChunkEvent)]
        assert len(text_events) == 4  # 3 content chunks + 1 done=True
        assert text_events[0].content == "Hello"
        assert text_events[1].content == " world"
        assert text_events[2].content == "!"
        assert text_events[3].done is True

    @pytest.mark.asyncio
    async def test_writes_to_event_log(self, tmp_path: Any) -> None:
        agent = AgentCore()
        agent.state_machine.transition(AgentState.CONVERSING)
        agent.event_log = EventLog(db_path=tmp_path / "test.db")

        async def fake_stream(messages: Any, config: Any, **kwargs: Any):  # type: ignore[return]
            yield "Hello"

        with patch("clide.core.agent.stream_completion", side_effect=fake_stream):
            await collect_events(
                agent.agent_step(
                    messages=[{"role": "user", "content": "hi"}],
                    tools=[],
                    session_id="s1",
                    mode="chat",
                )
            )

        events = await agent.event_log.get_session("s1")
        assert len(events) == 1
        assert events[0]["event_type"] == "assistant_message"
        assert events[0]["content"] == "Hello"

    @pytest.mark.asyncio
    async def test_no_event_log_no_error(self) -> None:
        """No-tools path works without event_log configured."""
        agent = AgentCore()
        agent.state_machine.transition(AgentState.CONVERSING)

        async def fake_stream(messages: Any, config: Any, **kwargs: Any):  # type: ignore[return]
            yield "chunk"

        with patch("clide.core.agent.stream_completion", side_effect=fake_stream):
            events = await collect_events(
                agent.agent_step(
                    messages=[{"role": "user", "content": "hi"}],
                    tools=[],
                    session_id="s1",
                    mode="chat",
                )
            )

        assert any(isinstance(e, TextChunkEvent) for e in events)

    @pytest.mark.asyncio
    async def test_empty_stream_yields_done(self) -> None:
        agent = AgentCore()
        agent.state_machine.transition(AgentState.CONVERSING)

        async def fake_stream(messages: Any, config: Any, **kwargs: Any):  # type: ignore[return]
            return
            yield  # make it an async generator

        with patch("clide.core.agent.stream_completion", side_effect=fake_stream):
            events = await collect_events(
                agent.agent_step(
                    messages=[{"role": "user", "content": "hi"}],
                    tools=[],
                    session_id="s1",
                    mode="chat",
                )
            )

        text_events = [e for e in events if isinstance(e, TextChunkEvent)]
        # Only the done=True event
        assert len(text_events) == 1
        assert text_events[0].done is True
        assert text_events[0].content == ""


class TestAgentStepWithTools:
    """Tests for the tool-calling path."""

    @pytest.mark.asyncio
    async def test_single_tool_call_then_text(self) -> None:
        agent = AgentCore()
        agent.state_machine.transition(AgentState.CONVERSING)

        registry = MagicMock()
        registry.execute_tool = AsyncMock(
            return_value=ToolResult(call_id="c1", result={"data": "ok"}, success=True)
        )
        agent.tool_registry = registry

        tool_resp = make_tool_response([("search", {"q": "test"}, "c1")])
        text_resp = make_text_response("Here are the results.")

        with patch(
            "clide.core.agent.complete_with_tools",
            new_callable=AsyncMock,
            side_effect=[tool_resp, text_resp],
        ):
            events = await collect_events(
                agent.agent_step(
                    messages=[
                        {"role": "system", "content": "sys"},
                        {"role": "user", "content": "search for test"},
                    ],
                    tools=[{"type": "function", "function": {"name": "search"}}],
                    session_id="s1",
                    mode="chat",
                )
            )

        tool_call_events = [e for e in events if isinstance(e, ToolCallEvent)]
        tool_result_events = [e for e in events if isinstance(e, ToolResultEvent)]
        text_events = [e for e in events if isinstance(e, TextChunkEvent)]

        assert len(tool_call_events) == 1
        assert tool_call_events[0].tool_name == "search"
        assert len(tool_result_events) == 1
        assert tool_result_events[0].success is True
        assert len(text_events) == 1
        assert text_events[0].done is True
        assert text_events[0].content == "Here are the results."

    @pytest.mark.asyncio
    async def test_state_transitions_emitted(self) -> None:
        agent = AgentCore()
        agent.state_machine.transition(AgentState.CONVERSING)

        registry = MagicMock()
        registry.execute_tool = AsyncMock(
            return_value=ToolResult(call_id="c1", result="ok", success=True)
        )
        agent.tool_registry = registry

        tool_resp = make_tool_response([("t1", {}, "c1")])
        text_resp = make_text_response("Done")

        with patch(
            "clide.core.agent.complete_with_tools",
            new_callable=AsyncMock,
            side_effect=[tool_resp, text_resp],
        ):
            events = await collect_events(
                agent.agent_step(
                    messages=[{"role": "user", "content": "do"}],
                    tools=[{"type": "function", "function": {"name": "t1"}}],
                    session_id="s1",
                    mode="chat",
                )
            )

        state_events = [e for e in events if isinstance(e, StateChangeEvent)]
        assert len(state_events) == 2
        assert state_events[0].new_state == "working"
        assert state_events[1].new_state == "conversing"

    @pytest.mark.asyncio
    async def test_dedup_skips_repeated_call(self) -> None:
        agent = AgentCore()
        agent.state_machine.transition(AgentState.CONVERSING)

        registry = MagicMock()
        registry.execute_tool = AsyncMock(
            return_value=ToolResult(call_id="c1", result="ok", success=True)
        )
        agent.tool_registry = registry

        # LLM calls same tool twice in one response
        tool_resp = make_tool_response(
            [("search", {"q": "test"}, "c1"), ("search", {"q": "test"}, "c2")]
        )
        text_resp = make_text_response("Done")

        with patch(
            "clide.core.agent.complete_with_tools",
            new_callable=AsyncMock,
            side_effect=[tool_resp, text_resp],
        ):
            events = await collect_events(
                agent.agent_step(
                    messages=[{"role": "user", "content": "search"}],
                    tools=[{"type": "function", "function": {"name": "search"}}],
                    session_id="s1",
                    mode="chat",
                )
            )

        tool_call_events = [e for e in events if isinstance(e, ToolCallEvent)]
        assert len(tool_call_events) == 1  # Only 1, the duplicate was skipped
        # execute_tool should only be called once
        assert registry.execute_tool.call_count == 1

    @pytest.mark.asyncio
    async def test_max_phases_exhausted_yields_fallback(self) -> None:
        agent = AgentCore()
        agent.state_machine.transition(AgentState.CONVERSING)

        registry = MagicMock()
        registry.execute_tool = AsyncMock(
            return_value=ToolResult(call_id="c1", result="ok", success=True)
        )
        agent.tool_registry = registry

        # LLM always returns tool calls, never text — will exhaust phases
        # Use unique call_ids to avoid dedup
        call_counter = [0]

        def make_unique_tool_resp(*args: Any, **kwargs: Any) -> MagicMock:
            call_counter[0] += 1
            return make_tool_response(
                [("search", {"q": f"test{call_counter[0]}"}, f"c{call_counter[0]}")]
            )

        with patch(
            "clide.core.agent.complete_with_tools",
            new_callable=AsyncMock,
            side_effect=make_unique_tool_resp,
        ):
            events = await collect_events(
                agent.agent_step(
                    messages=[{"role": "user", "content": "search"}],
                    tools=[{"type": "function", "function": {"name": "search"}}],
                    session_id="s1",
                    mode="chat",
                    phase_size=2,
                    max_phases=2,
                )
            )

        text_events = [e for e in events if isinstance(e, TextChunkEvent)]
        assert any(e.done for e in text_events)
        # The last text event should be the fallback message
        final = [e for e in text_events if e.done][-1]
        assert "research" in final.content.lower() or "summarize" in final.content.lower()

    @pytest.mark.asyncio
    async def test_llm_call_events_with_usage(self) -> None:
        agent = AgentCore()
        agent.state_machine.transition(AgentState.CONVERSING)

        registry = MagicMock()
        registry.execute_tool = AsyncMock(
            return_value=ToolResult(call_id="c1", result="ok", success=True)
        )
        agent.tool_registry = registry

        tool_resp = make_tool_response([("t1", {}, "c1")])
        text_resp = make_text_response("Done")

        with patch(
            "clide.core.agent.complete_with_tools",
            new_callable=AsyncMock,
            side_effect=[tool_resp, text_resp],
        ):
            events = await collect_events(
                agent.agent_step(
                    messages=[{"role": "user", "content": "do"}],
                    tools=[{"type": "function", "function": {"name": "t1"}}],
                    session_id="s1",
                    mode="chat",
                )
            )

        llm_events = [e for e in events if isinstance(e, LLMCallEvent)]
        assert len(llm_events) >= 2  # At least one per complete_with_tools call
        assert llm_events[0].prompt_tokens == 100
        assert llm_events[0].completion_tokens == 50

    @pytest.mark.asyncio
    async def test_tool_events_written_to_event_log(self, tmp_path: Any) -> None:
        agent = AgentCore()
        agent.state_machine.transition(AgentState.CONVERSING)
        agent.event_log = EventLog(db_path=tmp_path / "test.db")

        registry = MagicMock()
        registry.execute_tool = AsyncMock(
            return_value=ToolResult(call_id="c1", result={"found": True}, success=True)
        )
        agent.tool_registry = registry

        tool_resp = make_tool_response([("search", {"q": "test"}, "c1")])
        text_resp = make_text_response("Found it.")

        with patch(
            "clide.core.agent.complete_with_tools",
            new_callable=AsyncMock,
            side_effect=[tool_resp, text_resp],
        ):
            await collect_events(
                agent.agent_step(
                    messages=[{"role": "user", "content": "search"}],
                    tools=[{"type": "function", "function": {"name": "search"}}],
                    session_id="s1",
                    mode="chat",
                )
            )

        log_events = await agent.event_log.get_session("s1")
        types = [e["event_type"] for e in log_events]
        assert "tool_call" in types
        assert "tool_result" in types
        assert "assistant_message" in types

    @pytest.mark.asyncio
    async def test_tool_call_event_has_correct_fields(self) -> None:
        agent = AgentCore()
        agent.state_machine.transition(AgentState.CONVERSING)

        registry = MagicMock()
        registry.execute_tool = AsyncMock(
            return_value=ToolResult(call_id="call-42", result="result", success=True)
        )
        agent.tool_registry = registry

        tool_resp = make_tool_response([("my_tool", {"param": "value"}, "call-42")])
        text_resp = make_text_response("Done")

        with patch(
            "clide.core.agent.complete_with_tools",
            new_callable=AsyncMock,
            side_effect=[tool_resp, text_resp],
        ):
            events = await collect_events(
                agent.agent_step(
                    messages=[{"role": "user", "content": "use tool"}],
                    tools=[{"type": "function", "function": {"name": "my_tool"}}],
                    session_id="s1",
                    mode="chat",
                )
            )

        tool_call_events = [e for e in events if isinstance(e, ToolCallEvent)]
        assert len(tool_call_events) == 1
        tc = tool_call_events[0]
        assert tc.tool_name == "my_tool"
        assert tc.arguments == {"param": "value"}
        assert tc.call_id == "call-42"

    @pytest.mark.asyncio
    async def test_tool_result_error_path(self) -> None:
        agent = AgentCore()
        agent.state_machine.transition(AgentState.CONVERSING)

        registry = MagicMock()
        registry.execute_tool = AsyncMock(
            return_value=ToolResult(call_id="c1", result=None, success=False, error="timeout")
        )
        agent.tool_registry = registry

        tool_resp = make_tool_response([("flaky_tool", {}, "c1")])
        text_resp = make_text_response("Sorry, the tool failed.")

        with patch(
            "clide.core.agent.complete_with_tools",
            new_callable=AsyncMock,
            side_effect=[tool_resp, text_resp],
        ):
            events = await collect_events(
                agent.agent_step(
                    messages=[{"role": "user", "content": "run"}],
                    tools=[{"type": "function", "function": {"name": "flaky_tool"}}],
                    session_id="s1",
                    mode="chat",
                )
            )

        result_events = [e for e in events if isinstance(e, ToolResultEvent)]
        assert len(result_events) == 1
        assert result_events[0].success is False
        assert result_events[0].error == "timeout"
        assert result_events[0].result is None

    @pytest.mark.asyncio
    async def test_checkpoint_event_emitted_in_phase_2(self) -> None:
        """CheckpointEvent is emitted when entering phase 2."""
        agent = AgentCore()
        agent.state_machine.transition(AgentState.CONVERSING)

        registry = MagicMock()
        call_counter = [0]

        async def execute_side_effect(name: str, args: Any) -> ToolResult:
            return ToolResult(call_id=f"c{call_counter[0]}", result="ok", success=True)

        registry.execute_tool = AsyncMock(side_effect=execute_side_effect)
        agent.tool_registry = registry

        # Phase 1: one tool call per step, phase_size=1 so we move to phase 2 after 1 tool
        # Step 1 in phase 1: tool call
        # Phase 2 checkpoint response (text, but from complete_with_tools)
        # Step 1 in phase 2: text response -> done
        unique_counter = [0]

        def side_effect(*args: Any, **kwargs: Any) -> MagicMock:
            unique_counter[0] += 1
            n = unique_counter[0]
            if n == 1:
                # Phase 1 step 1: tool call
                return make_tool_response([("tool_a", {"x": n}, f"c{n}")])
            elif n == 2:
                # Phase 2 checkpoint
                return make_text_response("Checkpoint summary")
            else:
                # Phase 2 step 1: text
                return make_text_response("Final answer")

        with patch(
            "clide.core.agent.complete_with_tools",
            new_callable=AsyncMock,
            side_effect=side_effect,
        ):
            events = await collect_events(
                agent.agent_step(
                    messages=[{"role": "user", "content": "do"}],
                    tools=[{"type": "function", "function": {"name": "tool_a"}}],
                    session_id="s1",
                    mode="chat",
                    phase_size=1,
                    max_phases=2,
                )
            )

        checkpoint_events = [e for e in events if isinstance(e, CheckpointEvent)]
        assert len(checkpoint_events) == 1
        assert checkpoint_events[0].content == "Checkpoint summary"
        assert checkpoint_events[0].phase == 1
        assert checkpoint_events[0].total_phases == 2


class TestMakeSessionId:
    def test_returns_uuid_string(self) -> None:
        sid = AgentCore._make_session_id()
        assert isinstance(sid, str)
        assert len(sid) == 36  # UUID format

    def test_unique_ids(self) -> None:
        assert AgentCore._make_session_id() != AgentCore._make_session_id()
