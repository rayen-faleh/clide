"""Tests for the workshop mode."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clide.autonomy.models import (
    WorkshopPlan,
    WorkshopSession,
    WorkshopStep,
)
from clide.autonomy.workshop import (
    WORKSHOP_PLAN_PROMPT,
    WORKSHOP_REVIEW_PROMPT,
    WORKSHOP_STEP_PROMPT,
    WorkshopRunner,
)
from clide.core.llm import LLMConfig


def _make_llm_response(content: str) -> MagicMock:
    """Create a mock LLM response with the given content."""
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    response.choices[0].finish_reason = "stop"
    response.choices[0].message.tool_calls = None
    return response


def _make_tool_response_with_calls(tool_calls: list[dict[str, Any]]) -> MagicMock:
    """Create a mock LLM response with tool calls."""
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].finish_reason = "tool_calls"
    response.choices[0].message.content = None

    mock_tool_calls = []
    for tc in tool_calls:
        mock_tc = MagicMock()
        mock_tc.id = tc.get("id", "call_123")
        mock_tc.function.name = tc["name"]
        mock_tc.function.arguments = tc.get("arguments", "{}")
        mock_tool_calls.append(mock_tc)

    response.choices[0].message.tool_calls = mock_tool_calls
    response.choices[0].message.model_dump.return_value = {
        "role": "assistant",
        "content": None,
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
    return response


class TestWorkshopModels:
    """Tests for workshop data models."""

    def test_workshop_step_defaults(self) -> None:
        step = WorkshopStep(id="s1", description="Do something")
        assert step.status == "pending"
        assert step.result_summary == ""
        assert step.tools_needed == []
        assert step.success_criteria == ""

    def test_workshop_plan_creation(self) -> None:
        steps = [
            WorkshopStep(id="s1", description="Step 1"),
            WorkshopStep(id="s2", description="Step 2"),
        ]
        plan = WorkshopPlan(
            objective="Test objective",
            approach="Test approach",
            steps=steps,
        )
        assert plan.objective == "Test objective"
        assert len(plan.steps) == 2

    def test_workshop_session_defaults(self) -> None:
        session = WorkshopSession(
            id="sess1",
            goal_id="g1",
            goal_description="Test goal",
        )
        assert session.status == "active"
        assert session.current_step_index == 0
        assert session.plan is None
        assert session.inner_dialogue == []

    def test_workshop_session_with_plan(self) -> None:
        plan = WorkshopPlan(
            objective="Test",
            approach="approach",
            steps=[WorkshopStep(id="s1", description="step")],
        )
        session = WorkshopSession(
            id="sess1",
            goal_id="g1",
            goal_description="Test goal",
            plan=plan,
        )
        assert session.plan is not None
        assert len(session.plan.steps) == 1


class TestWorkshopRunnerInit:
    """Tests for WorkshopRunner initialization."""

    def test_init_basic(self) -> None:
        config = LLMConfig()
        runner = WorkshopRunner(
            llm_config=config,
            goal_id="g1",
            goal_description="Test goal",
        )
        assert runner.session.goal_id == "g1"
        assert runner.session.goal_description == "Test goal"
        assert runner.session.status == "active"
        assert runner._cancelled is False
        assert runner._paused is False

    def test_init_with_all_params(self) -> None:
        config = LLMConfig()
        broadcast = AsyncMock()
        tool_exec = AsyncMock()
        runner = WorkshopRunner(
            llm_config=config,
            goal_id="g1",
            goal_description="Test goal",
            personality_context="test personality",
            tools_context="tool1, tool2",
            tool_definitions=[{"function": {"name": "tool1"}}],
            broadcast_fn=broadcast,
            tool_execute_fn=tool_exec,
        )
        assert runner.personality_context == "test personality"
        assert runner.tools_context == "tool1, tool2"
        assert len(runner.tool_definitions) == 1
        assert runner._broadcast_fn is broadcast
        assert runner._tool_execute_fn is tool_exec


class TestWorkshopRunnerPauseResumeCancel:
    """Tests for pause, resume, and cancel operations."""

    def test_pause(self) -> None:
        runner = WorkshopRunner(
            llm_config=LLMConfig(),
            goal_id="g1",
            goal_description="Test",
        )
        runner.pause()
        assert runner._paused is True
        assert runner.session.status == "paused"

    def test_resume(self) -> None:
        runner = WorkshopRunner(
            llm_config=LLMConfig(),
            goal_id="g1",
            goal_description="Test",
        )
        runner.pause()
        runner.resume()
        assert runner._paused is False
        assert runner.session.status == "active"

    def test_cancel(self) -> None:
        runner = WorkshopRunner(
            llm_config=LLMConfig(),
            goal_id="g1",
            goal_description="Test",
        )
        runner.cancel()
        assert runner._cancelled is True
        assert runner._paused is False
        assert runner.session.status == "abandoned"

    def test_cancel_while_paused(self) -> None:
        runner = WorkshopRunner(
            llm_config=LLMConfig(),
            goal_id="g1",
            goal_description="Test",
        )
        runner.pause()
        runner.cancel()
        assert runner._cancelled is True
        assert runner._paused is False


class TestWorkshopRunnerPlanGeneration:
    """Tests for plan generation."""

    @pytest.mark.asyncio
    async def test_generate_plan_success(self) -> None:
        plan_json = (
            '{"objective": "test objective", "approach": "test approach", '
            '"steps": [{"description": "step 1", "tools_needed": ["t1"], '
            '"success_criteria": "done when x"}]}'
        )
        mock_response = _make_llm_response(plan_json)

        runner = WorkshopRunner(
            llm_config=LLMConfig(),
            goal_id="g1",
            goal_description="Test goal",
        )

        with patch("clide.autonomy.workshop.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)
            plan = await runner._generate_plan()

        assert plan is not None
        assert plan.objective == "test objective"
        assert plan.approach == "test approach"
        assert len(plan.steps) == 1
        assert plan.steps[0].description == "step 1"
        assert plan.steps[0].tools_needed == ["t1"]

    @pytest.mark.asyncio
    async def test_generate_plan_failure_returns_none(self) -> None:
        runner = WorkshopRunner(
            llm_config=LLMConfig(),
            goal_id="g1",
            goal_description="Test goal",
        )

        with patch("clide.autonomy.workshop.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(side_effect=Exception("LLM error"))
            plan = await runner._generate_plan()

        assert plan is None

    @pytest.mark.asyncio
    async def test_generate_plan_with_multiple_steps(self) -> None:
        plan_json = (
            '{"objective": "research topic", "approach": "systematic", '
            '"steps": ['
            '{"description": "step 1", "tools_needed": [], "success_criteria": "c1"},'
            '{"description": "step 2", "tools_needed": ["t1"], "success_criteria": "c2"},'
            '{"description": "step 3", "tools_needed": ["t2", "t3"], "success_criteria": "c3"}'
            "]}"
        )
        mock_response = _make_llm_response(plan_json)

        runner = WorkshopRunner(
            llm_config=LLMConfig(),
            goal_id="g1",
            goal_description="Research",
        )

        with patch("clide.autonomy.workshop.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)
            plan = await runner._generate_plan()

        assert plan is not None
        assert len(plan.steps) == 3


class TestWorkshopRunnerStepExecution:
    """Tests for step execution."""

    @pytest.mark.asyncio
    async def test_execute_step_complete_action(self) -> None:
        step_json = (
            '{"inner_dialogue": "Already done", "action": "complete", '
            '"result_summary": "Done previously"}'
        )
        mock_response = _make_llm_response(step_json)

        runner = WorkshopRunner(
            llm_config=LLMConfig(),
            goal_id="g1",
            goal_description="Test",
        )
        runner.session.plan = WorkshopPlan(objective="test", approach="test", steps=[])

        step = WorkshopStep(
            id="s1",
            description="Test step",
            status="in_progress",
        )

        with patch("clide.autonomy.workshop.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)
            await runner._execute_step(0, step)

        assert step.result_summary == "Done previously"

    @pytest.mark.asyncio
    async def test_execute_step_skip_action(self) -> None:
        step_json = (
            '{"inner_dialogue": "Not needed", "action": "skip", "skip_reason": "Already covered"}'
        )
        mock_response = _make_llm_response(step_json)

        runner = WorkshopRunner(
            llm_config=LLMConfig(),
            goal_id="g1",
            goal_description="Test",
        )
        runner.session.plan = WorkshopPlan(objective="test", approach="test", steps=[])

        step = WorkshopStep(
            id="s1",
            description="Test step",
            status="in_progress",
        )

        with patch("clide.autonomy.workshop.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)
            await runner._execute_step(0, step)

        assert step.status == "skipped"
        assert step.result_summary == "Already covered"

    @pytest.mark.asyncio
    async def test_execute_step_records_inner_dialogue(self) -> None:
        step_json = (
            '{"inner_dialogue": "Thinking about this...", "action": "complete", '
            '"result_summary": "Done"}'
        )
        mock_response = _make_llm_response(step_json)

        runner = WorkshopRunner(
            llm_config=LLMConfig(),
            goal_id="g1",
            goal_description="Test",
        )
        runner.session.plan = WorkshopPlan(objective="test", approach="test", steps=[])

        step = WorkshopStep(id="s1", description="Test step")

        with patch("clide.autonomy.workshop.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)
            await runner._execute_step(0, step)

        assert len(runner.session.inner_dialogue) >= 1
        assert "Thinking about this..." in runner.session.inner_dialogue[0]["content"]


class TestWorkshopRunnerFullRun:
    """Tests for the full workshop run lifecycle."""

    @pytest.mark.asyncio
    async def test_run_abandoned_on_plan_failure(self) -> None:
        broadcast = AsyncMock()
        runner = WorkshopRunner(
            llm_config=LLMConfig(),
            goal_id="g1",
            goal_description="Test",
            broadcast_fn=broadcast,
        )

        with patch("clide.autonomy.workshop.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(side_effect=Exception("LLM error"))
            await runner.run()

        assert runner.session.status == "abandoned"
        # Should broadcast ended
        broadcast.assert_called()
        last_call_args = broadcast.call_args[0][0]
        assert last_call_args.get("workshop_ended") is True
        assert last_call_args["status"] == "abandoned"

    @pytest.mark.asyncio
    async def test_run_completed_successfully(self) -> None:
        plan_json = (
            '{"objective": "test", "approach": "do it", '
            '"steps": [{"description": "step 1", "tools_needed": [], '
            '"success_criteria": "done"}]}'
        )
        step_json = (
            '{"inner_dialogue": "Working", "action": "complete", '
            '"result_summary": "Completed step 1"}'
        )
        review_json = '{"review": "Everything went well."}'

        broadcast = AsyncMock()
        call_count = 0

        async def mock_acompletion(**kwargs: Any) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _make_llm_response(plan_json)
            elif call_count == 2:
                return _make_llm_response(step_json)
            else:
                return _make_llm_response(review_json)

        runner = WorkshopRunner(
            llm_config=LLMConfig(),
            goal_id="g1",
            goal_description="Test goal",
            broadcast_fn=broadcast,
        )

        with patch("clide.autonomy.workshop.litellm") as mock_litellm:
            mock_litellm.acompletion = mock_acompletion
            await runner.run()

        assert runner.session.status == "completed"
        assert runner.session.plan is not None
        assert runner.session.plan.steps[0].status == "completed"

    @pytest.mark.asyncio
    async def test_run_cancelled_during_steps(self) -> None:
        plan_json = (
            '{"objective": "test", "approach": "do it", '
            '"steps": [{"description": "step 1"}, {"description": "step 2"}]}'
        )
        step_json = '{"inner_dialogue": "Working", "action": "complete", "result_summary": "Done"}'

        call_count = 0
        runner = WorkshopRunner(
            llm_config=LLMConfig(),
            goal_id="g1",
            goal_description="Test",
        )

        async def mock_acompletion(**kwargs: Any) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _make_llm_response(plan_json)
            else:
                # Cancel after first step
                runner.cancel()
                return _make_llm_response(step_json)

        with patch("clide.autonomy.workshop.litellm") as mock_litellm:
            mock_litellm.acompletion = mock_acompletion
            await runner.run()

        assert runner.session.status == "abandoned"

    @pytest.mark.asyncio
    async def test_run_broadcasts_plan(self) -> None:
        plan_json = (
            '{"objective": "test obj", "approach": "test approach", '
            '"steps": [{"description": "s1", "tools_needed": [], '
            '"success_criteria": "c1"}]}'
        )
        step_json = '{"inner_dialogue": "ok", "action": "complete", "result_summary": "Done"}'
        review_json = '{"review": "Good."}'

        broadcast = AsyncMock()
        call_count = 0

        async def mock_acompletion(**kwargs: Any) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _make_llm_response(plan_json)
            elif call_count == 2:
                return _make_llm_response(step_json)
            else:
                return _make_llm_response(review_json)

        runner = WorkshopRunner(
            llm_config=LLMConfig(),
            goal_id="g1",
            goal_description="Test",
            broadcast_fn=broadcast,
        )

        with patch("clide.autonomy.workshop.litellm") as mock_litellm:
            mock_litellm.acompletion = mock_acompletion
            await runner.run()

        # Find the plan broadcast call
        plan_calls = [c for c in broadcast.call_args_list if c[0][0].get("workshop_plan")]
        assert len(plan_calls) == 1
        plan_event = plan_calls[0][0][0]
        assert plan_event["objective"] == "test obj"

    @pytest.mark.asyncio
    async def test_run_broadcasts_step_updates(self) -> None:
        plan_json = (
            '{"objective": "test", "approach": "do it", "steps": [{"description": "step 1"}]}'
        )
        step_json = '{"inner_dialogue": "ok", "action": "complete", "result_summary": "Done"}'
        review_json = '{"review": "Good."}'

        broadcast = AsyncMock()
        call_count = 0

        async def mock_acompletion(**kwargs: Any) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _make_llm_response(plan_json)
            elif call_count == 2:
                return _make_llm_response(step_json)
            else:
                return _make_llm_response(review_json)

        runner = WorkshopRunner(
            llm_config=LLMConfig(),
            goal_id="g1",
            goal_description="Test",
            broadcast_fn=broadcast,
        )

        with patch("clide.autonomy.workshop.litellm") as mock_litellm:
            mock_litellm.acompletion = mock_acompletion
            await runner.run()

        step_updates = [c for c in broadcast.call_args_list if c[0][0].get("workshop_step_update")]
        # Should have at least 2 step updates (in_progress + completed)
        assert len(step_updates) >= 2


class TestWorkshopRunnerToolExecution:
    """Tests for tool execution within workshop steps."""

    @pytest.mark.asyncio
    async def test_execute_tools_for_step(self) -> None:
        # First call: tool call, second call: text response
        tool_response = _make_tool_response_with_calls(
            [{"name": "web_search", "arguments": '{"query": "test"}', "id": "c1"}]
        )
        text_response = _make_llm_response("Found the answer.")

        tool_result = MagicMock()
        tool_result.success = True
        tool_result.result = "search results here"
        tool_result.error = None

        tool_exec = AsyncMock(return_value=tool_result)
        broadcast = AsyncMock()

        runner = WorkshopRunner(
            llm_config=LLMConfig(),
            goal_id="g1",
            goal_description="Test",
            tool_definitions=[{"function": {"name": "web_search"}}],
            tool_execute_fn=tool_exec,
            broadcast_fn=broadcast,
        )

        step = WorkshopStep(
            id="s1",
            description="Search for info",
            success_criteria="found info",
        )

        with patch(
            "clide.autonomy.workshop.complete_with_tools",
            new_callable=AsyncMock,
            side_effect=[tool_response, text_response],
        ):
            await runner._execute_tools_for_step(step)

        tool_exec.assert_called_once_with("web_search", {"query": "test"})
        assert step.result_summary == "Found the answer."

    @pytest.mark.asyncio
    async def test_execute_tools_cancelled(self) -> None:
        runner = WorkshopRunner(
            llm_config=LLMConfig(),
            goal_id="g1",
            goal_description="Test",
            tool_definitions=[{"function": {"name": "tool1"}}],
            tool_execute_fn=AsyncMock(),
        )
        runner._cancelled = True

        step = WorkshopStep(id="s1", description="Test step")
        await runner._execute_tools_for_step(step)

        # Should not have called tools
        runner._tool_execute_fn.assert_not_called()  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_execute_tools_no_definitions(self) -> None:
        runner = WorkshopRunner(
            llm_config=LLMConfig(),
            goal_id="g1",
            goal_description="Test",
            tool_definitions=[],
        )

        step = WorkshopStep(id="s1", description="Test step")
        # Should return immediately without error
        await runner._execute_tools_for_step(step)


class TestWorkshopPrompts:
    """Tests for workshop prompt templates."""

    def test_plan_prompt_has_placeholders(self) -> None:
        assert "{goal_description}" in WORKSHOP_PLAN_PROMPT
        assert "{tools_context}" in WORKSHOP_PLAN_PROMPT

    def test_step_prompt_has_placeholders(self) -> None:
        assert "{objective}" in WORKSHOP_STEP_PROMPT
        assert "{step_description}" in WORKSHOP_STEP_PROMPT
        assert "{step_index}" in WORKSHOP_STEP_PROMPT

    def test_review_prompt_has_placeholders(self) -> None:
        assert "{objective}" in WORKSHOP_REVIEW_PROMPT
        assert "{completed_steps}" in WORKSHOP_REVIEW_PROMPT

    def test_plan_prompt_formats_correctly(self) -> None:
        """Personality context is now in system message, not in the prompt."""
        result = WORKSHOP_PLAN_PROMPT.format(
            goal_description="Test goal",
            tools_context="tool1, tool2",
        )
        assert "Test goal" in result
        assert "tool1, tool2" in result
