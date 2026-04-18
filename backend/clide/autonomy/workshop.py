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

from clide.autonomy.models import GoalStatus, WorkshopPlan, WorkshopSession, WorkshopStep
from clide.core.agent_events import (
    TextChunkEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from clide.core.llm import LLMConfig, _build_model_name
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
        amem: Any = None,
        agent_name: str = "Clide",
        tool_skills: dict[str, str] | None = None,
        agent_step_fn: Any = None,
        context_builder: Any = None,
        goal_manager: Any = None,
    ) -> None:
        self.llm_config = llm_config
        self._agent_step_fn = agent_step_fn
        self._amem = amem
        self._agent_name = agent_name
        self._tool_skills = tool_skills or {}
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
        self._context_builder = context_builder
        self._goal_manager = goal_manager
        self._cancelled = False
        self._paused = False
        self._dialogue_memory_count: int = 0
        # Track memory IDs written during this session to prevent self-poisoning
        self._session_memory_ids: set[str] = set()
        # Cumulative conversation history shared across plan/step/review phases
        self._session_messages: list[dict[str, Any]] = []

    async def run(self) -> None:
        """Main workshop loop: plan -> execute steps -> review."""
        self._dialogue_memory_count = 0
        self._session_memory_ids = set()
        self._session_messages = [self._build_system_message()]
        try:
            # Phase 1: Generate plan
            plan = await self._generate_plan()
            if not plan or self._cancelled:
                self.session.status = "abandoned"
                await self._broadcast_ended("abandoned", "Failed to generate plan")
                await self._abandon_goal()
                return

            self.session.plan = plan
            await self._broadcast_plan()

            # Store plan in memory
            await self._store_memory(
                f"{self._agent_name} entered the Workshop to work on: "
                f"{plan.objective}. Approach: {plan.approach}. "
                f"Steps: {', '.join(s.description for s in plan.steps)}",
                {"type": "workshop", "phase": "plan"},
            )

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

                # Mark the backing goal as completed
                await self._complete_goal()

                # Store completion summary in memory
                step_results = "; ".join(
                    f"{s.description}: {s.result_summary or s.status}"
                    for s in (self.session.plan.steps if self.session.plan else [])
                )
                await self._store_memory(
                    f"{self._agent_name} completed a Workshop session on: "
                    f"{self.session.goal_description}. "
                    f"Results: {step_results[:500]}",
                    {"type": "workshop", "phase": "completed"},
                )
            else:
                self.session.status = "abandoned"
                await self._broadcast_ended("abandoned", "Workshop was cancelled")
                await self._abandon_goal()

        except Exception:
            logger.exception("Workshop session failed")
            self.session.status = "abandoned"
            await self._broadcast_ended("abandoned", "Workshop failed due to an error")
            await self._abandon_goal()

    async def _generate_plan(self) -> WorkshopPlan | None:
        """Generate a structured plan from the goal."""
        prompt = WORKSHOP_PLAN_PROMPT.format(
            goal_description=self.session.goal_description,
            tools_context=self.tools_context,
        )
        context_section = await self._recall_context(
            self.session.goal_description, memory_limit=5
        )

        messages = self._build_messages(prompt, extra_context=context_section)
        try:
            if self._agent_step_fn:
                text = ""
                async for event in self._agent_step_fn(
                    messages=messages,
                    tools=[],
                    session_id=str(uuid.uuid4()),
                    mode="workshop",
                    purpose="workshop_plan",
                ):
                    if isinstance(event, TextChunkEvent) and event.content:
                        text += event.content
            else:
                model_name = _build_model_name(self.llm_config)
                kwargs: dict[str, Any] = {
                    "model": model_name,
                    "messages": messages,
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

            # Grow cumulative session context: plan prompt + response
            self._session_messages.append({"role": "user", "content": prompt})
            self._session_messages.append({"role": "assistant", "content": text})

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
        context_section = await self._recall_context(step.description, memory_limit=3)

        messages = self._build_messages(prompt, extra_context=context_section)
        try:
            if self._agent_step_fn:
                text = ""
                async for event in self._agent_step_fn(
                    messages=messages,
                    tools=[],
                    session_id=str(uuid.uuid4()),
                    mode="workshop",
                    purpose="workshop_step_decision",
                ):
                    if isinstance(event, TextChunkEvent) and event.content:
                        text += event.content
            else:
                model_name = _build_model_name(self.llm_config)
                step_kwargs: dict[str, Any] = {
                    "model": model_name,
                    "messages": messages,
                    "max_tokens": self.llm_config.max_tokens,
                    "stream": False,
                }
                if self.llm_config.api_base:
                    step_kwargs["api_base"] = self.llm_config.api_base
                response = await litellm.acompletion(**step_kwargs)
                text = str(response.choices[0].message.content or "")

            # Grow cumulative session context: step decision prompt + response
            self._session_messages.append({"role": "user", "content": prompt})
            self._session_messages.append({"role": "assistant", "content": text})

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
            elif action == "complete":
                step.status = "completed"
                step.result_summary = data.get("result_summary", "Completed")
            else:
                # action == "use_tools": execute tools
                if self.tool_definitions and self._agent_step_fn:
                    await self._execute_tools_for_step(step)

                if not step.result_summary:
                    step.result_summary = data.get("result_summary", "Step completed with tools")
                step.status = "completed"

            # Store individual step result in A-MEM
            if step.result_summary and step.status in ("completed", "skipped"):
                await self._store_memory(
                    f"{self._agent_name} completed Workshop step {index + 1}: "
                    f"{step.description}. Result: {step.result_summary}",
                    {
                        "type": "workshop_step",
                        "phase": "step_result",
                        "step_index": str(index),
                        "goal_id": self.session.goal_id,
                    },
                )

        except Exception:
            logger.exception("Failed to execute workshop step %d", index)
            step.result_summary = "Step failed due to error"

    async def _execute_tools_for_step(self, step: WorkshopStep) -> None:
        """Execute tools for a workshop step via the unified agent loop."""
        if not self.tool_definitions or not self._agent_step_fn:
            return

        tool_prompt = (
            f"You are in your Workshop. Use the available tools to "
            f"complete this step:\n"
            f"Step: {step.description}\n"
            f"Success criteria: {step.success_criteria}\n\n"
            f"Use tools as needed, then respond with your findings."
        )

        messages: list[dict[str, Any]] = self._build_messages(tool_prompt)
        session_id = str(uuid.uuid4())
        full_text = ""

        async for event in self._agent_step_fn(
            messages=messages,
            tools=self.tool_definitions,
            session_id=session_id,
            mode="workshop",
            phase_size=10,
            max_phases=1,
            purpose="workshop_step",
        ):
            if isinstance(event, TextChunkEvent):
                if event.content:
                    full_text += event.content
                if event.done and full_text:
                    await self._inner_dialogue(full_text)
                    step.result_summary = full_text[:500]
            elif isinstance(event, ToolCallEvent):
                if self._broadcast_fn:
                    try:
                        await self._broadcast_fn({
                            "tool_call": True,
                            "tool_name": event.tool_name,
                            "arguments": event.arguments,
                            "call_id": event.call_id,
                        })
                    except Exception:
                        logger.warning("Workshop tool call broadcast failed", exc_info=True)
            elif isinstance(event, ToolResultEvent):
                preview = str(event.result)[:200] if event.result else ""
                await self._inner_dialogue(f"Used tool -> {preview}")
                if self._broadcast_fn:
                    try:
                        await self._broadcast_fn({
                            "tool_result": True,
                            "call_id": event.call_id,
                            "result": event.result,
                            "error": event.error,
                            "success": event.success,
                        })
                    except Exception:
                        logger.warning("Workshop tool result broadcast failed", exc_info=True)

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

        messages = self._build_messages(prompt)
        try:
            if self._agent_step_fn:
                text = ""
                async for event in self._agent_step_fn(
                    messages=messages,
                    tools=[],
                    session_id=str(uuid.uuid4()),
                    mode="workshop",
                    purpose="workshop_review",
                ):
                    if isinstance(event, TextChunkEvent) and event.content:
                        text += event.content
            else:
                model_name = _build_model_name(self.llm_config)
                rev_kwargs: dict[str, Any] = {
                    "model": model_name,
                    "messages": messages,
                    "max_tokens": self.llm_config.max_tokens,
                    "stream": False,
                }
                if self.llm_config.api_base:
                    rev_kwargs["api_base"] = self.llm_config.api_base
                response = await litellm.acompletion(**rev_kwargs)
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

        # Store meaningful dialogue excerpts in A-MEM (capped at 5 per session)
        if len(content) > 100 and self._dialogue_memory_count < 5:
            self._dialogue_memory_count += 1
            await self._store_memory(
                f"{self._agent_name}'s workshop reflection: {content[:600]}",
                {
                    "type": "workshop_dialogue",
                    "phase": "inner_dialogue",
                    "goal_id": self.session.goal_id,
                },
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

    async def _complete_goal(self) -> None:
        """Mark the backing goal as completed in the goal manager."""
        if not self._goal_manager:
            return
        try:
            await self._goal_manager.update(
                self.session.goal_id,
                status=GoalStatus.COMPLETED,
                progress=1.0,
            )
            logger.info("Workshop goal %s marked as completed", self.session.goal_id)
        except Exception:
            logger.warning("Failed to mark workshop goal as completed", exc_info=True)

    async def _abandon_goal(self) -> None:
        """Mark the backing goal as abandoned in the goal manager."""
        if not self._goal_manager:
            return
        try:
            await self._goal_manager.update(
                self.session.goal_id,
                status=GoalStatus.ABANDONED,
            )
            logger.info("Workshop goal %s marked as abandoned", self.session.goal_id)
        except Exception:
            logger.warning("Failed to mark workshop goal as abandoned", exc_info=True)

    async def _store_memory(self, content: str, metadata: dict[str, str]) -> None:
        """Store a workshop event in A-MEM and track the ID to prevent self-poisoning."""
        if not self._amem:
            return
        try:
            zettel = await self._amem.remember(content, metadata=metadata)
            self._session_memory_ids.add(zettel.id)
        except Exception:
            logger.warning("Failed to store workshop memory", exc_info=True)

    async def _recall_context(self, query: str, memory_limit: int = 5) -> str:
        """Recall memories + cross-mode events relevant to a query.

        Explicitly excludes:
        - thinking-mode events (EventLog filter via include_modes)
        - ``type=thought`` memories (autonomous thought memories from A-MEM)
        - memories written during the current session (prevent self-poisoning)
        """
        if not self._context_builder:
            return ""
        result = await self._context_builder.build(
            query=query,
            current_mode="workshop",
            memory_limit=memory_limit,
            event_limit=5,
            include_modes=["chat"],
            exclude_types=["thought"],
            exclude_ids=self._session_memory_ids,
        )
        parts: list[str] = []
        if result.memory_text:
            parts.append(f"## Relevant Memories\n{result.memory_text}")
        if result.cross_mode_text:
            parts.append(f"## Recent Activity\n{result.cross_mode_text}")
        return "\n\n".join(parts)

    def _build_system_message(self) -> dict[str, Any]:
        """Build the static system message: persona + workshop framing + tool skills."""
        system_parts = []
        if self.personality_context:
            system_parts.append(self.personality_context)

        system_parts.append(
            "You are in your personal Workshop — a private, focused work session. "
            "You are thinking out loud to yourself. There is no one else here. "
            "Stay fully in character. Do not address anyone directly."
        )

        if self._tool_skills:
            skill_lines = ["## Tool Usage Guidelines\n"]
            for tool_name, skill_text in self._tool_skills.items():
                skill_lines.append(f"### {tool_name}\n{skill_text}\n")
            system_parts.append("\n".join(skill_lines))

        return {"role": "system", "content": "\n\n".join(system_parts)}

    def _build_messages(self, prompt: str, extra_context: str = "") -> list[dict[str, Any]]:
        """Return the cumulative session conversation + a new user turn.

        If this is the very first call (session_messages is empty, e.g. called
        outside of ``run()``), falls back to building a fresh message list so
        direct calls to ``_generate_plan`` / ``_execute_step`` in tests still work.

        ``extra_context`` is injected into the system message for this call only
        (it is not persisted to ``_session_messages``).
        """
        if self._session_messages:
            # Clone the cumulative history; optionally enrich system message
            messages = list(self._session_messages)
            if extra_context:
                enriched_system = messages[0]["content"] + "\n\n" + extra_context
                messages[0] = {"role": "system", "content": enriched_system}
        else:
            # Fallback: build a fresh list (used when run() was not called first)
            system_msg = self._build_system_message()
            if extra_context:
                enriched = system_msg["content"] + "\n\n" + extra_context
                system_msg = {"role": "system", "content": enriched}
            messages = [system_msg]

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
