"""Workshop mode -- autonomous multi-step goal pursuit."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import litellm

from clide.autonomy.models import WorkshopPlan, WorkshopSession, WorkshopStep
from clide.core.llm import LLMConfig, _build_model_name, complete_with_tools
from clide.memory.processor import _extract_json

logger = logging.getLogger(__name__)


def _robust_extract_json(text: str) -> dict[str, Any]:
    """Extract JSON from LLM response, handling markdown, think tags, truncation.

    Strategy: strip tags/markdown, find first { and last }, try to parse.
    If truncated (no closing }), attempt to close it and extract what we can.
    """
    # Strip think tags
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"</?think>", "", text).strip()

    # Try _extract_json first (handles code blocks etc.)
    try:
        return _extract_json(text)  # type: ignore[no-any-return]
    except (json.JSONDecodeError, ValueError):
        pass

    # Find first { and last }
    first_brace = text.find("{")
    last_brace = text.rfind("}")

    if first_brace == -1:
        raise ValueError("No JSON object found in response")

    if last_brace > first_brace:
        # Normal case: we have both braces
        candidate = text[first_brace : last_brace + 1]
        try:
            return json.loads(candidate)  # type: ignore[no-any-return]
        except json.JSONDecodeError:
            pass

    # Truncated: no closing brace or parse failed
    # Extract what we can with regex
    result: dict[str, Any] = {}
    for key in (
        "inner_dialogue",
        "objective",
        "approach",
        "action",
        "review",
        "skip_reason",
        "result_summary",
        "thought",
    ):
        match = re.search(rf'"{key}"\s*:\s*"((?:[^"\\]|\\.)*)"', text, re.DOTALL)
        if match:
            result[key] = match.group(1).replace("\\n", "\n").replace('\\"', '"')

    if not result:
        raise ValueError("Could not extract any fields from response")

    return result


WORKSHOP_PLAN_PROMPT = """You are about to enter your Workshop \
-- a focused work session to pursue a specific goal. \
Create a structured execution plan.

Goal: {goal_description}

Available tools: {tools_context}

Create a plan with 3-8 concrete steps. Each step should be actionable and \
achievable using your available tools. Be specific about what each step will \
accomplish.

Respond with ONLY this JSON:
{{"objective": "what you're trying to achieve", \
"approach": "your high-level strategy (1-2 sentences)", \
"steps": [{{"description": "what to do", "tools_needed": ["tool1"], \
"success_criteria": "how to know this is done"}}]}}"""

WORKSHOP_STEP_PROMPT = """You are in your Workshop, actively working on a goal.

Overall objective: {objective}
Approach: {approach}

Current step ({step_index}/{total_steps}): {step_description}
Success criteria: {success_criteria}
Tools available for this step: {tools_for_step}

Previous steps completed:
{previous_results}

Think out loud about what you need to do for this step. Stay in character.
Then decide: should you use tools, skip this step, or mark it complete \
based on previous work?

Respond with ONLY this JSON:
{{"inner_dialogue": "your thinking (2-5 sentences, in character)", \
"action": "use_tools", "skip_reason": "", "result_summary": ""}}

For action, use one of:
- "use_tools" -- you need to call tools to complete this step
- "skip" -- skip this step (provide skip_reason)
- "complete" -- this step is already done from previous work \
(provide result_summary)"""

WORKSHOP_REVIEW_PROMPT = """You just finished all steps in your Workshop session.

Goal: {objective}

Steps completed:
{completed_steps}

Review what you accomplished. Summarize the overall result in 2-4 sentences, \
in character. Be honest about what went well and what didn't.

Respond with ONLY this JSON:
{{"review": "your summary of what was accomplished"}}"""


class WorkshopRunner:
    """Manages a workshop session: plan generation, step execution, review."""

    def __init__(
        self,
        llm_config: LLMConfig,
        goal_id: str,
        goal_description: str,
        personality_context: str = "",
        tools_context: str = "",
        tool_definitions: list[dict[str, Any]] | None = None,
        broadcast_fn: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
        tool_execute_fn: (Callable[[str, dict[str, Any]], Awaitable[Any]] | None) = None,
    ) -> None:
        self.llm_config = llm_config
        self.session = WorkshopSession(
            id=str(uuid.uuid4()),
            goal_id=goal_id,
            goal_description=goal_description,
        )
        self.personality_context = personality_context
        self.tools_context = tools_context
        self.tool_definitions = tool_definitions or []
        self._broadcast_fn = broadcast_fn
        self._tool_execute_fn = tool_execute_fn
        self._cancelled = False
        self._paused = False

    async def run(self) -> None:
        """Main workshop loop: plan -> execute steps -> review."""
        try:
            # Phase 1: Generate plan
            plan = await self._generate_plan()
            if not plan or self._cancelled:
                self.session.status = "abandoned"
                await self._broadcast_ended("abandoned", "Failed to generate plan")
                return

            self.session.plan = plan
            await self._broadcast_plan()

            # Phase 2: Execute each step
            for i, step in enumerate(plan.steps):
                if self._cancelled:
                    break

                # Wait while paused
                while self._paused and not self._cancelled:
                    await asyncio.sleep(1)

                if self._cancelled:
                    break

                self.session.current_step_index = i
                step.status = "in_progress"
                self.session.updated_at = datetime.now(UTC)
                await self._broadcast_step_update(i, step)

                await self._execute_step(i, step)

                if step.status == "in_progress":
                    step.status = "completed"
                self.session.updated_at = datetime.now(UTC)
                await self._broadcast_step_update(i, step)

            # Phase 3: Review
            if not self._cancelled:
                await self._review()
                self.session.status = "completed"
                await self._broadcast_ended("completed", "Workshop completed successfully")
            else:
                self.session.status = "abandoned"
                await self._broadcast_ended("abandoned", "Workshop was cancelled")

        except Exception:
            logger.exception("Workshop session failed")
            self.session.status = "abandoned"
            await self._broadcast_ended("abandoned", "Workshop failed due to an error")

    async def _generate_plan(self) -> WorkshopPlan | None:
        """Generate a structured plan from the goal."""
        prompt = WORKSHOP_PLAN_PROMPT.format(
            goal_description=self.session.goal_description,
            tools_context=self.tools_context,
        )

        try:
            model_name = _build_model_name(self.llm_config)
            kwargs: dict[str, Any] = {
                "model": model_name,
                "messages": self._build_messages(prompt),
                "max_tokens": self.llm_config.max_tokens,
                "stream": False,
            }
            if self.llm_config.api_base:
                kwargs["api_base"] = self.llm_config.api_base

            response = await litellm.acompletion(**kwargs)
            text = str(response.choices[0].message.content or "")

            # Strip think tags (Mistral thinking models)
            text = re.sub(r"</?think>", "", text).strip()

            if not text:
                logger.warning("Empty plan response from LLM")
                return None

            logger.debug("Plan response (%d chars): %s", len(text), text[:300])

            try:
                data = _robust_extract_json(text)
            except (json.JSONDecodeError, ValueError):
                logger.warning("Failed to parse plan JSON, attempting regex fallback")
                obj_match = re.search(r'"objective"\s*:\s*"([^"]*)"', text)
                app_match = re.search(r'"approach"\s*:\s*"([^"]*)"', text)
                if obj_match:
                    data = {
                        "objective": obj_match.group(1),
                        "approach": app_match.group(1) if app_match else "",
                        "steps": [],
                    }
                    step_matches = re.findall(r'"description"\s*:\s*"([^"]*)"', text)
                    for desc in step_matches:
                        data["steps"].append({"description": desc})
                else:
                    return None

            steps = []
            for s in data.get("steps", []):
                steps.append(
                    WorkshopStep(
                        id=str(uuid.uuid4()),
                        description=s.get("description", ""),
                        tools_needed=s.get("tools_needed", []),
                        success_criteria=s.get("success_criteria", ""),
                    )
                )

            return WorkshopPlan(
                objective=data.get("objective", self.session.goal_description),
                approach=data.get("approach", ""),
                steps=steps,
            )
        except Exception:
            logger.exception("Failed to generate workshop plan")
            return None

    async def _execute_step(self, index: int, step: WorkshopStep) -> None:
        """Execute a single step: think, use tools if needed, evaluate."""
        previous_results = ""
        if self.session.plan:
            previous_results = "\n".join(
                f"  Step {j + 1}: {s.result_summary or 'completed'}"
                for j, s in enumerate(self.session.plan.steps[:index])
                if s.status in ("completed", "skipped")
            )

        prompt = WORKSHOP_STEP_PROMPT.format(
            objective=(self.session.plan.objective if self.session.plan else ""),
            approach=(self.session.plan.approach if self.session.plan else ""),
            step_index=index + 1,
            total_steps=(len(self.session.plan.steps) if self.session.plan else 0),
            step_description=step.description,
            success_criteria=step.success_criteria,
            tools_for_step=(", ".join(step.tools_needed) if step.tools_needed else "any available"),
            previous_results=previous_results or "(none yet)",
        )

        try:
            model_name = _build_model_name(self.llm_config)
            kwargs: dict[str, Any] = {
                "model": model_name,
                "messages": self._build_messages(prompt),
                "max_tokens": self.llm_config.max_tokens,
                "stream": False,
            }
            if self.llm_config.api_base:
                kwargs["api_base"] = self.llm_config.api_base

            response = await litellm.acompletion(**kwargs)
            text = str(response.choices[0].message.content or "")

            try:
                data = _robust_extract_json(text)
            except (json.JSONDecodeError, ValueError):
                # Extract just the dialogue text, stripping any JSON/markdown artifacts
                clean = re.sub(r"```(?:json)?\s*", "", text)
                clean = re.sub(r"```\s*$", "", clean)
                clean = re.sub(r'"inner_dialogue"\s*:\s*"?', "", clean)
                clean = clean.strip().strip('"').strip("{").strip()
                logger.warning("Failed to parse step JSON, using cleaned text as dialogue")
                data = {
                    "inner_dialogue": clean[:500] if clean else "Working on this step...",
                    "action": "complete",
                }

            inner_dialogue = data.get("inner_dialogue", "Working on this step...")
            action = data.get("action", "complete")

            # Broadcast inner dialogue
            await self._inner_dialogue(inner_dialogue)

            if action == "skip":
                step.status = "skipped"
                step.result_summary = data.get("skip_reason", "Skipped")
                await self._inner_dialogue(f"Skipping this step: {step.result_summary}")
                return

            if action == "complete":
                step.result_summary = data.get("result_summary", "Completed")
                return

            # action == "use_tools": execute tools
            if self.tool_definitions and self._tool_execute_fn:
                await self._execute_tools_for_step(step)

            if not step.result_summary:
                step.result_summary = data.get("result_summary", "Step completed with tools")

        except Exception:
            logger.exception("Failed to execute workshop step %d", index)
            step.result_summary = "Step failed due to error"

    async def _execute_tools_for_step(self, step: WorkshopStep) -> None:
        """Execute tools for a workshop step using the tool-aware LLM pattern."""
        if not self.tool_definitions or not self._tool_execute_fn:
            return

        tool_prompt = (
            f"You are in your Workshop. Use the available tools to "
            f"complete this step:\n"
            f"Step: {step.description}\n"
            f"Success criteria: {step.success_criteria}\n\n"
            f"Use tools as needed, then respond with your findings."
        )

        messages: list[dict[str, Any]] = self._build_messages(tool_prompt)

        # Tool loop (max 10 iterations)
        for _iteration in range(10):
            if self._cancelled:
                break

            # Rate limit: brief pause between LLM calls to avoid API throttling
            if _iteration > 0:
                await asyncio.sleep(1)

            try:
                response = await complete_with_tools(
                    messages, self.llm_config, self.tool_definitions
                )
            except Exception:
                logger.exception("Tool call failed in workshop step")
                break

            choice = response.choices[0]

            if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
                messages.append(choice.message.model_dump())

                for tool_call in choice.message.tool_calls:
                    func = tool_call.function
                    tool_name = func.name
                    try:
                        arguments = (
                            json.loads(func.arguments)
                            if isinstance(func.arguments, str)
                            else func.arguments
                        )
                    except (json.JSONDecodeError, TypeError):
                        arguments = {}

                    # Broadcast tool call
                    if self._broadcast_fn:
                        await self._broadcast_fn(
                            {
                                "tool_call": True,
                                "tool_name": tool_name,
                                "arguments": arguments,
                                "call_id": tool_call.id,
                            }
                        )

                    # Execute tool
                    result = await self._tool_execute_fn(tool_name, arguments)

                    # Broadcast tool result
                    if self._broadcast_fn:
                        await self._broadcast_fn(
                            {
                                "tool_result": True,
                                "call_id": tool_call.id,
                                "result": (
                                    result.result if hasattr(result, "result") else str(result)
                                ),
                                "error": (result.error if hasattr(result, "error") else None),
                                "success": (result.success if hasattr(result, "success") else True),
                            }
                        )

                    # Broadcast as inner dialogue too
                    result_preview = str(result.result if hasattr(result, "result") else result)[
                        :200
                    ]
                    await self._inner_dialogue(f"Used {tool_name} -> {result_preview}")

                    result_content = (
                        json.dumps(result.result)
                        if hasattr(result, "result") and result.success
                        else (f"Error: {result.error}" if hasattr(result, "error") else str(result))
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": result_content,
                        }
                    )

                continue
            else:
                # Text response -- step is done
                text_result = choice.message.content or ""
                if text_result:
                    await self._inner_dialogue(text_result)
                    step.result_summary = text_result[:500]
                break

    async def _review(self) -> None:
        """Final review of the workshop session."""
        if not self.session.plan:
            return

        completed_steps = "\n".join(
            f"  {j + 1}. {s.description}: {s.result_summary or s.status}"
            for j, s in enumerate(self.session.plan.steps)
        )

        prompt = WORKSHOP_REVIEW_PROMPT.format(
            objective=self.session.plan.objective,
            completed_steps=completed_steps,
        )

        try:
            model_name = _build_model_name(self.llm_config)
            kwargs: dict[str, Any] = {
                "model": model_name,
                "messages": self._build_messages(prompt),
                "max_tokens": self.llm_config.max_tokens,
                "stream": False,
            }
            if self.llm_config.api_base:
                kwargs["api_base"] = self.llm_config.api_base

            response = await litellm.acompletion(**kwargs)
            text = str(response.choices[0].message.content or "")

            try:
                data = _robust_extract_json(text)
                review = data.get("review", text)
            except (json.JSONDecodeError, ValueError):
                # Strip markdown artifacts from review text
                review = re.sub(r"```(?:json)?\s*", "", text)
                review = re.sub(r"</?think>", "", review).strip()

            await self._inner_dialogue(f"Workshop review: {review}")

        except Exception:
            logger.exception("Failed to generate workshop review")

    async def _inner_dialogue(self, content: str) -> None:
        """Record and broadcast agent's self-conversation."""
        entry: dict[str, Any] = {
            "role": "assistant",
            "content": content,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        self.session.inner_dialogue.append(entry)

        if self._broadcast_fn:
            await self._broadcast_fn(
                {
                    "workshop_dialogue": True,
                    "session_id": self.session.id,
                    "content": content,
                }
            )

    async def _broadcast_plan(self) -> None:
        """Broadcast the workshop plan to frontend."""
        if not self._broadcast_fn or not self.session.plan:
            return
        await self._broadcast_fn(
            {
                "workshop_plan": True,
                "session_id": self.session.id,
                "objective": self.session.plan.objective,
                "approach": self.session.plan.approach,
                "steps": [
                    {
                        "id": s.id,
                        "description": s.description,
                        "tools_needed": s.tools_needed,
                        "success_criteria": s.success_criteria,
                        "status": s.status,
                    }
                    for s in self.session.plan.steps
                ],
            }
        )

    async def _broadcast_step_update(self, index: int, step: WorkshopStep) -> None:
        """Broadcast step status change."""
        if not self._broadcast_fn:
            return
        await self._broadcast_fn(
            {
                "workshop_step_update": True,
                "session_id": self.session.id,
                "step_index": index,
                "status": step.status,
                "result_summary": step.result_summary,
            }
        )

    async def _broadcast_ended(self, status: str, summary: str) -> None:
        """Broadcast workshop session end."""
        if not self._broadcast_fn:
            return
        await self._broadcast_fn(
            {
                "workshop_ended": True,
                "session_id": self.session.id,
                "status": status,
                "summary": summary,
            }
        )

    def _build_messages(self, prompt: str) -> list[dict[str, Any]]:
        """Build message list with system persona + user task prompt.

        Separates personality context into system role (identity anchoring)
        and keeps the task instructions as user role. This prevents the LLM
        from treating the persona as instructions from another person.
        """
        messages: list[dict[str, Any]] = []
        if self.personality_context:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        f"{self.personality_context}\n\n"
                        "You are in your personal Workshop — a private, focused work session. "
                        "You are thinking out loud to yourself. There is no one else here. "
                        "Stay fully in character. Do not address anyone directly."
                    ),
                }
            )
        messages.append({"role": "user", "content": prompt})
        return messages

    def pause(self) -> None:
        """Pause the workshop (user interrupted)."""
        self._paused = True
        self.session.status = "paused"
        logger.info("Workshop paused: %s", self.session.id)

    def resume(self) -> None:
        """Resume a paused workshop."""
        self._paused = False
        self.session.status = "active"
        logger.info("Workshop resumed: %s", self.session.id)

    def cancel(self) -> None:
        """Cancel the workshop."""
        self._cancelled = True
        self._paused = False
        self.session.status = "abandoned"
        logger.info("Workshop cancelled: %s", self.session.id)
