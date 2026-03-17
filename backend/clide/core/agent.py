"""Core agent implementation."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import json as json_mod
import logging
import random
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import litellm

from clide.api.schemas import AgentState
from clide.autonomy.models import ThoughtType
from clide.core.llm import LLMConfig, _build_model_name, complete_with_tools, stream_completion
from clide.core.prompts import build_system_prompt
from clide.core.state import StateMachine

if TYPE_CHECKING:
    from clide.autonomy.goals import GoalManager
    from clide.character.character import Character
    from clide.core.conversation_store import ConversationStore
    from clide.core.cost import CostTracker
    from clide.memory.amem import AMem
    from clide.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

THOUGHT_TYPE_WEIGHTS: dict[str, int] = {
    ThoughtType.MIND_WANDERING: 40,
    ThoughtType.SELF_REFLECTION: 25,
    ThoughtType.SCENARIO_SIMULATION: 15,
    ThoughtType.GOAL_ORIENTED: 15,
    ThoughtType.OBSERVATION: 5,
}


class AgentCore:
    """Core agent that processes messages and manages state."""

    def __init__(
        self,
        system_prompt: str = "",
        llm_config: LLMConfig | None = None,
        amem: AMem | None = None,
        character: Character | None = None,
        cost_tracker: CostTracker | None = None,
        goal_manager: GoalManager | None = None,
        conversation_store: ConversationStore | None = None,
        born_at: datetime | None = None,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        self.state_machine = StateMachine(initial_state=AgentState.IDLE)
        self.llm_config = llm_config or LLMConfig()
        self.system_prompt = system_prompt
        self.conversation_history: list[dict[str, Any]] = []
        self._max_history_length = 50  # Keep last N messages
        self.amem = amem
        self.character = character
        self.cost_tracker = cost_tracker
        self.goal_manager = goal_manager
        self.conversation_store = conversation_store
        self._history_loaded = False
        self.born_at = born_at
        self.tool_registry = tool_registry
        self._tool_event_callback: Any = None  # Set by websocket handler
        self._workshop_runner: Any = None  # WorkshopRunner when in workshop mode
        self._recent_topics: list[str] = []  # Track last N thought topics
        self._topic_history_size = 6  # Remember last 6 topics
        self.tool_phase_size = 10  # Tool calls per phase before checkpoint
        self.tool_max_phases = 3  # Maximum number of phases
        self._background_tasks: set[asyncio.Task[None]] = set()
        # Persona drift mitigation
        self._persona_manager: Any = None  # Set from main.py
        self._persona_settings: Any = None  # PersonaSettings from config
        self._agent_name: str = "Clide"
        self._last_thought_metadata: dict[str, str] = {}

    @staticmethod
    def _format_age(dt: datetime) -> str:
        """Format a datetime as a human-readable relative age string."""
        now = datetime.now(UTC)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        age = now - dt
        if age.days > 0:
            return f"{age.days}d ago"
        elif age.seconds >= 3600:
            return f"{age.seconds // 3600}h ago"
        elif age.seconds >= 60:
            return f"{age.seconds // 60}m ago"
        else:
            return "just now"

    def get_state(self) -> AgentState:
        """Get current agent state."""
        return self.state_machine.state

    def set_tool_event_callback(self, callback: Any) -> None:
        """Set callback for tool events (called by WebSocket handler)."""
        self._tool_event_callback = callback

    def _track_task(self, coro: Any) -> None:
        """Create and track a background task to prevent GC and enable cleanup."""
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    @staticmethod
    def _ensure_valid_message_order(messages: list[dict[str, Any]]) -> None:
        """Ensure the last message is not 'assistant' (Mistral requirement).

        Mistral rejects requests where the last message has role=assistant.
        If that happens, append a minimal user continuation prompt.
        """
        if messages and messages[-1].get("role") == "assistant":
            messages.append({"role": "user", "content": "Continue."})

    async def _build_messages_with_reinforcement(self, system: str) -> list[dict[str, Any]]:
        """Build message list with periodic persona reinforcement.

        Injects system-role persona reminders every N user messages
        to combat attention decay (47% drift reduction per research).
        """
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}]

        # Get persona summary for reinforcement
        persona_summary = ""
        interval = 0
        if self._persona_manager and self._persona_settings:
            interval = self._persona_settings.reinforcement_interval
            if interval > 0:
                persona_summary = await self._persona_manager.get_summary(self.system_prompt)

        if not persona_summary or interval <= 0:
            messages.extend(self.conversation_history)
            return messages

        user_msg_count = 0
        for msg in self.conversation_history:
            if msg.get("role") == "user":
                user_msg_count += 1
                if user_msg_count > 0 and user_msg_count % interval == 0:
                    messages.append(
                        self._persona_manager.build_reinforcement_message(persona_summary)
                    )
            messages.append(msg)

        return messages

    async def _maybe_summarize_history(self) -> None:
        """Summarize old conversation history if it exceeds the threshold."""
        if not self._persona_settings:
            # Fall back to simple trimming
            if len(self.conversation_history) > self._max_history_length:
                self.conversation_history = self.conversation_history[-self._max_history_length :]
            return

        threshold = self._persona_settings.history_summarize_threshold
        keep_recent = self._persona_settings.history_summary_keep_recent

        if len(self.conversation_history) <= threshold:
            return

        if not self._persona_settings.summarize_history or not self._persona_manager:
            # Fall back to simple trimming
            self.conversation_history = self.conversation_history[-self._max_history_length :]
            return

        # Split: old messages to summarize, recent to keep
        old_messages = self.conversation_history[:-keep_recent]
        recent_messages = self.conversation_history[-keep_recent:]

        summary = await self._persona_manager.summarize_history(old_messages, self._agent_name)

        if summary:
            self.conversation_history = [
                {
                    "role": "system",
                    "content": f"[Previous conversation summary: {summary}]",
                },
                *recent_messages,
            ]
            logger.info(
                "Summarized %d messages into summary (%d chars), keeping %d recent",
                len(old_messages),
                len(summary),
                len(recent_messages),
            )
        else:
            # Fallback: simple trimming
            self.conversation_history = self.conversation_history[-self._max_history_length :]

    async def _process_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        phase_size: int = 10,
        max_phases: int = 3,
    ) -> str:
        """Execute the agentic tool loop with phased checkpoints.

        Every ``phase_size`` tool calls, forces a text checkpoint where the LLM
        summarises progress and plans next steps.  Also detects duplicate tool
        calls (same name + args) and skips them with a warning message.

        Returns the final text response.
        """
        tool_call_count = 0
        seen_calls: set[str] = set()  # Track "tool_name:args" for dedup

        for current_phase in range(1, max_phases + 1):
            # --- Phase checkpoint (between phases, not before the first) ---
            if current_phase > 1:
                logger.info(
                    "Tool phase %d checkpoint (after %d calls)",
                    current_phase - 1,
                    tool_call_count,
                )

                checkpoint_prompt = (
                    "You've made several tool calls. Briefly summarize what you've "
                    "found so far and what you plan to do next. Be concise."
                )
                messages.append({"role": "user", "content": checkpoint_prompt})

                try:
                    model_name = _build_model_name(self.llm_config)
                    checkpoint_kwargs: dict[str, Any] = {
                        "model": model_name,
                        "messages": messages,
                        "max_tokens": 200,
                        "stream": False,
                    }
                    if self.llm_config.api_base:
                        checkpoint_kwargs["api_base"] = self.llm_config.api_base

                    checkpoint_response = await litellm.acompletion(**checkpoint_kwargs)
                    checkpoint_text = checkpoint_response.choices[0].message.content or ""
                    messages.append({"role": "assistant", "content": checkpoint_text})

                    # Broadcast checkpoint via callback
                    if self._tool_event_callback:
                        try:
                            await self._tool_event_callback(
                                {
                                    "checkpoint": True,
                                    "content": checkpoint_text,
                                    "phase": current_phase - 1,
                                    "total_phases": max_phases,
                                    "tool_call_count": tool_call_count,
                                }
                            )
                        except Exception:
                            logger.warning("Checkpoint callback failed", exc_info=True)

                except Exception:
                    logger.warning("Checkpoint generation failed", exc_info=True)

            # --- Inner loop: up to phase_size tool calls per phase ---
            phase_tool_count = 0
            for _step in range(phase_size):
                logger.info(
                    "Tool loop step %d (phase %d/%d, %d total tool calls)",
                    phase_tool_count + 1,
                    current_phase,
                    max_phases,
                    tool_call_count,
                )
                self._ensure_valid_message_order(messages)
                try:
                    response = await complete_with_tools(messages, self.llm_config, tools)
                except Exception:
                    logger.exception(
                        "LLM call failed in tool loop (phase %d, step %d)",
                        current_phase,
                        phase_tool_count + 1,
                    )
                    if tool_call_count > 0:
                        return (
                            "I used some tools but couldn't finish processing the results. "
                            "The tool results are shown above — you can ask me to try again."
                        )
                    raise

                choice = response.choices[0]
                logger.debug(
                    "LLM response: finish_reason=%s, has_tool_calls=%s, has_content=%s",
                    choice.finish_reason,
                    bool(choice.message.tool_calls)
                    if hasattr(choice.message, "tool_calls")
                    else "N/A",
                    bool(choice.message.content),
                )

                # Check if LLM wants to call tools
                if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
                    logger.info(
                        "LLM requested %d tool call(s)",
                        len(choice.message.tool_calls),
                    )

                    # Transition to WORKING and broadcast state change
                    if self.state_machine.can_transition(AgentState.WORKING):
                        self.state_machine.transition(AgentState.WORKING, "tool call")
                        if self._tool_event_callback:
                            with contextlib.suppress(Exception):
                                await self._tool_event_callback(
                                    {
                                        "state_change": True,
                                        "previous_state": "conversing",
                                        "new_state": "working",
                                        "reason": "tool call",
                                    }
                                )

                    # Append assistant message with tool calls
                    messages.append(choice.message.model_dump())

                    # Execute each tool call
                    for tool_call in choice.message.tool_calls:
                        func = tool_call.function
                        tool_name = func.name
                        try:
                            arguments = (
                                json_mod.loads(func.arguments)
                                if isinstance(func.arguments, str)
                                else func.arguments
                            )
                        except (json_mod.JSONDecodeError, TypeError):
                            arguments = {}
                        call_id = tool_call.id

                        # --- Dedup check ---
                        args_str = (
                            func.arguments
                            if isinstance(func.arguments, str)
                            else json_mod.dumps(func.arguments, sort_keys=True)
                        )
                        call_signature = f"{tool_name}:{args_str}"

                        if call_signature in seen_calls:
                            logger.warning(
                                "Duplicate tool call detected: %s — skipping",
                                tool_name,
                            )
                            messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": call_id,
                                    "content": (
                                        f"DUPLICATE: You already called {tool_name} with "
                                        f"these exact arguments. The result was the same. "
                                        f"Do NOT call this tool again with the same "
                                        f"arguments. Try a different approach or respond "
                                        f"with text."
                                    ),
                                }
                            )
                            continue

                        seen_calls.add(call_signature)

                        logger.info(
                            "Executing tool: %s(args=%s)",
                            tool_name,
                            str(arguments)[:200],
                        )

                        # Broadcast tool call BEFORE execution (shows "executing" state)
                        if self._tool_event_callback:
                            try:
                                await self._tool_event_callback(
                                    {
                                        "tool_call": True,
                                        "tool_name": tool_name,
                                        "arguments": arguments,
                                        "call_id": call_id,
                                    }
                                )
                            except Exception:
                                logger.warning("Tool call callback failed", exc_info=True)

                        # Execute via registry
                        assert self.tool_registry is not None
                        result = await self.tool_registry.execute_tool(tool_name, arguments)

                        logger.info(
                            "Tool %s result: success=%s, result_preview=%s",
                            tool_name,
                            result.success,
                            str(result.result)[:150]
                            if result.success
                            else f"ERROR: {result.error}",
                        )

                        # Broadcast tool result AFTER execution
                        if self._tool_event_callback:
                            try:
                                await self._tool_event_callback(
                                    {
                                        "tool_result": True,
                                        "call_id": call_id,
                                        "result": result.result if result.success else None,
                                        "error": result.error if not result.success else None,
                                        "success": result.success,
                                    }
                                )
                            except Exception:
                                logger.warning("Tool result callback failed", exc_info=True)

                        # Append tool result message for LLM
                        result_content = (
                            json_mod.dumps(result.result)
                            if result.success
                            else f"Error: {result.error}"
                        )
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": call_id,
                                "content": result_content,
                            }
                        )

                        tool_call_count += 1
                        phase_tool_count += 1

                    # Transition back to CONVERSING and broadcast
                    if self.state_machine.state == AgentState.WORKING:
                        self.state_machine.transition(AgentState.CONVERSING, "tool results ready")
                        if self._tool_event_callback:
                            with contextlib.suppress(Exception):
                                await self._tool_event_callback(
                                    {
                                        "state_change": True,
                                        "previous_state": "working",
                                        "new_state": "conversing",
                                        "reason": "tool results ready",
                                    }
                                )

                    # Loop: call LLM again with tool results
                    continue

                else:
                    # LLM generated text response (no more tool calls)
                    text = choice.message.content or ""
                    logger.info(
                        "Tool loop done: %d phase(s), %d tool calls, %d chars",
                        current_phase,
                        tool_call_count,
                        len(text),
                    )
                    return text

        # Max phases exhausted
        logger.warning(
            "Tool loop exhausted all %d phases (%d total calls)",
            max_phases,
            tool_call_count,
        )
        return (
            "I've done extensive research with multiple tool calls. Let me summarize what I found."
        )

    async def process_message(self, content: str) -> AsyncIterator[str]:
        """Process a user message and yield response chunks.

        Transitions: IDLE -> CONVERSING (if needed), then streams response.
        Uses memory recall, character personality, and cost tracking when available.
        """
        # Load persisted history on first message
        if not self._history_loaded and self.conversation_store:
            try:
                self.conversation_history = await self.conversation_store.get_for_llm(
                    limit=self._max_history_length
                )
                logger.info(
                    "Loaded %d messages from conversation store",
                    len(self.conversation_history),
                )
            except Exception:
                logger.warning("Failed to load conversation history", exc_info=True)
            self._history_loaded = True

        # Handle /workshop command
        if content.strip().startswith("/workshop "):
            goal_desc = content.strip()[len("/workshop ") :].strip()
            if goal_desc:
                logger.info("User triggered workshop via command: %s", goal_desc[:100])
                goal_id = "user-workshop"
                if self.goal_manager:
                    try:
                        goal = await self.goal_manager.create(goal_desc)
                        goal_id = goal.id
                    except Exception:
                        logger.warning("Failed to create goal for workshop", exc_info=True)

                # Set up workshop broadcast using existing callback
                if self._tool_event_callback:
                    existing_cb = self._tool_event_callback

                    async def workshop_chat_broadcast(event: dict[str, Any]) -> None:
                        """Route workshop events through WebSocket."""
                        from clide.api.schemas import (
                            WorkshopDialoguePayload,
                            WorkshopEndedPayload,
                            WorkshopPlanPayload,
                            WorkshopStepUpdatePayload,
                            WSMessage,
                            WSMessageType,
                        )
                        from clide.api.websocket import manager as ws_manager

                        if event.get("workshop_dialogue"):
                            await ws_manager.broadcast(
                                WSMessage(
                                    type=WSMessageType.WORKSHOP_DIALOGUE,
                                    payload=WorkshopDialoguePayload(
                                        session_id=event["session_id"],
                                        content=event["content"],
                                    ).model_dump(),
                                )
                            )
                        elif event.get("workshop_plan"):
                            await ws_manager.broadcast(
                                WSMessage(
                                    type=WSMessageType.WORKSHOP_PLAN,
                                    payload=WorkshopPlanPayload(
                                        session_id=event["session_id"],
                                        objective=event["objective"],
                                        approach=event["approach"],
                                        steps=event["steps"],
                                    ).model_dump(),
                                )
                            )
                        elif event.get("workshop_step_update"):
                            await ws_manager.broadcast(
                                WSMessage(
                                    type=WSMessageType.WORKSHOP_STEP_UPDATE,
                                    payload=WorkshopStepUpdatePayload(
                                        session_id=event["session_id"],
                                        step_index=event["step_index"],
                                        status=event["status"],
                                        result_summary=event.get("result_summary", ""),
                                    ).model_dump(),
                                )
                            )
                        elif event.get("workshop_ended"):
                            await ws_manager.broadcast(
                                WSMessage(
                                    type=WSMessageType.WORKSHOP_ENDED,
                                    payload=WorkshopEndedPayload(
                                        session_id=event["session_id"],
                                        status=event["status"],
                                        summary=event.get("summary", ""),
                                    ).model_dump(),
                                )
                            )
                        elif event.get("tool_call") or event.get("tool_result"):
                            await existing_cb(event)

                    self.set_tool_event_callback(workshop_chat_broadcast)

                # Broadcast workshop started
                from clide.api.schemas import (
                    WorkshopStartedPayload,
                    WSMessage,
                    WSMessageType,
                )
                from clide.api.websocket import manager as ws_manager

                await ws_manager.broadcast(
                    WSMessage(
                        type=WSMessageType.WORKSHOP_STARTED,
                        payload=WorkshopStartedPayload(
                            session_id="pending",
                            goal_description=goal_desc,
                        ).model_dump(),
                    )
                )

                success = await self.enter_workshop(goal_id, goal_desc)
                if success:
                    yield f"Entering the Workshop to work on: {goal_desc}"
                else:
                    yield "I can't enter the Workshop right now — I might already be in one."
                return

        # Handle workshop interruption
        _was_in_workshop = False
        if self.state_machine.state == AgentState.WORKSHOP:
            _was_in_workshop = True
            if self._workshop_runner:
                self._workshop_runner.pause()
            self.state_machine.transition(AgentState.CONVERSING, "user interrupted workshop")

        # Transition to CONVERSING if currently IDLE
        if self.state_machine.state == AgentState.IDLE:
            logger.info("Agent state: IDLE -> CONVERSING (user message received)")
            self.state_machine.transition(AgentState.CONVERSING, "user message received")

        # Add user message to history
        self.conversation_history.append({"role": "user", "content": content})

        # Persist user message
        if self.conversation_store:
            try:
                await self.conversation_store.add_message("user", content)
            except Exception:
                logger.warning("Failed to persist user message", exc_info=True)

        # Recall relevant memories
        memory_context = ""
        if self.amem:
            try:
                relevant = await self.amem.recall(content, limit=5)
                if relevant:
                    logger.info("Recalled %d memories for context", len(relevant))
                    memory_context = "\n".join(
                        f"- {z.summary or z.content[:100]} [{self._format_age(z.created_at)}]"
                        for z in relevant
                    )
                else:
                    logger.debug("No memories found")
            except Exception:
                logger.warning("Failed to recall memories", exc_info=True)

        # Build enhanced system prompt
        personality = ""
        if self.character:
            personality = self.character.build_personality_prompt()

        tool_skills = self._load_tool_skills()
        reward_context = await self._gather_reward_context()

        system = build_system_prompt(
            self.system_prompt,
            personality_additions=personality,
            memory_context=memory_context,
            agent_born_at=self.born_at,
            tool_skills=tool_skills if tool_skills else None,
            reward_context=reward_context,
        )

        # Build messages for LLM (with persona reinforcement)
        messages = await self._build_messages_with_reinforcement(system)

        # --- Response generation (tools or streaming) ---
        tool_definitions: list[dict[str, Any]] = []
        if self.tool_registry:
            tool_definitions = self.tool_registry.get_tool_definitions_for_llm()
            logger.debug(
                "Tool registry: %d tool(s) available: %s",
                len(tool_definitions),
                [t["function"]["name"] for t in tool_definitions] if tool_definitions else "none",
            )
        else:
            logger.debug("No tool registry configured")

        full_response = ""
        if tool_definitions:
            # TOOL-AWARE PATH: non-streaming with tool loop
            logger.info("Using tool-aware path (%d tools)", len(tool_definitions))
            self._ensure_valid_message_order(messages)
            full_response = await self._process_with_tools(
                messages,
                tool_definitions,
                phase_size=self.tool_phase_size,
                max_phases=self.tool_max_phases,
            )
            yield full_response
        else:
            # SIMPLE PATH: streaming without tools (existing behavior)
            logger.info("Streaming LLM response (no tools)...")
            self._ensure_valid_message_order(messages)
            async for chunk in stream_completion(messages, self.llm_config):
                full_response += chunk
                yield chunk

        logger.info("LLM response complete (%d chars)", len(full_response))

        # Add assistant response to history
        self.conversation_history.append({"role": "assistant", "content": full_response})

        # Persist assistant message
        if self.conversation_store:
            try:
                await self.conversation_store.add_message("assistant", full_response)
            except Exception:
                logger.warning("Failed to persist assistant message", exc_info=True)

        # Summarize or trim history if needed
        await self._maybe_summarize_history()

        # Auto-resume workshop if it was paused
        if (
            _was_in_workshop
            and self._workshop_runner
            and self._workshop_runner.session.status == "paused"
        ):
            self._workshop_runner.resume()
            self.state_machine.transition(
                AgentState.WORKSHOP,
                "resuming workshop after conversation",
            )
            self._track_task(self._run_workshop())
        elif self.state_machine.state == AgentState.CONVERSING:
            # Normal transition to IDLE
            logger.info("Agent state: CONVERSING -> IDLE (response complete)")
            self.state_machine.transition(AgentState.IDLE, "response complete")

        # Fire-and-forget: store memory and update character in background
        logger.debug("Storing conversation to memory (background)")
        self._track_task(self._post_response_tasks(content, full_response))

    async def _post_response_tasks(self, content: str, full_response: str) -> None:
        """Background tasks after response: store memory and update character."""
        if self.amem:
            try:
                await self.amem.remember(
                    f"{self._agent_name}'s conversation — They asked: {content}\n"
                    f"I responded: {full_response[:500]}",
                    metadata={"type": "conversation"},
                )
            except Exception:
                logger.warning("Failed to store memory", exc_info=True)

        if self.character:
            try:
                self.character.mood.transition("content", 0.6, "conversation")
                await self.character.save()
            except Exception:
                logger.warning("Failed to update character", exc_info=True)

        # Lightweight goal review after conversation
        if self.goal_manager:
            try:
                active_goals = await self.goal_manager.get_active()
                for goal in active_goals:
                    # Simple heuristic: if goal description words appear in the
                    # conversation, nudge progress slightly
                    goal_words = set(goal.description.lower().split())
                    conversation_text = f"{content} {full_response}".lower()
                    matching_words = sum(
                        1 for w in goal_words if w in conversation_text and len(w) > 3
                    )
                    if matching_words >= 2:  # At least 2 significant words match
                        new_progress = min(1.0, goal.progress + 0.05)  # Small nudge
                        await self.goal_manager.update(goal.id, progress=new_progress)
                        logger.debug(
                            "Goal '%s' progress nudged to %.0f%% (conversation relevance)",
                            goal.description[:50],
                            new_progress * 100,
                        )
            except Exception:
                logger.warning("Failed to review goals after conversation", exc_info=True)

    async def _post_thought_tasks(self, thought: object, mood: str, intensity: float) -> None:
        """Background tasks after thinking: store thought and update character."""
        if self.amem:
            try:
                meta = getattr(thought, "metadata", {}) or {}
                await self.amem.remember(
                    f"{self._agent_name}'s private thought: "
                    f"{getattr(thought, 'content', str(thought))}",
                    metadata={
                        "type": "thought",
                        "source": "autonomous",
                        "topic": meta.get("topic", ""),
                        "follow_up": meta.get("follow_up", ""),
                    },
                )
            except Exception:
                logger.warning("Failed to store thought memory", exc_info=True)

        if self.character:
            try:
                self.character.mood.transition(mood, intensity, "autonomous thinking")
                await self.character.save()
            except Exception:
                logger.warning("Failed to update character after thinking", exc_info=True)

    async def _process_thought_goals(self, thought: object) -> None:
        """Process goal creation and updates from a thought's metadata."""
        if not self.goal_manager:
            logger.debug("No goal manager, skipping goal processing")
            return

        meta = getattr(thought, "metadata", {}) or {}
        logger.debug(
            "Processing thought goals: new_goal=%s, has_updates=%s",
            repr(meta.get("new_goal", ""))[:80],
            bool(meta.get("goal_updates", "")),
        )

        # Create new goal if proposed
        new_goal_desc = meta.get("new_goal", "")
        if new_goal_desc and isinstance(new_goal_desc, str) and new_goal_desc.strip():
            try:
                active_goals = await self.goal_manager.get_active()
                if len(active_goals) < 5:  # Max 5 active goals
                    await self.goal_manager.create(new_goal_desc.strip())
                    logger.info("Agent created new goal: %s", new_goal_desc[:80])
                else:
                    logger.debug("Goal creation skipped: already at max 5 active goals")
            except Exception:
                logger.warning("Failed to create goal", exc_info=True)

        # Process goal updates
        goal_updates_raw = meta.get("goal_updates", "")
        if goal_updates_raw and isinstance(goal_updates_raw, str):
            try:
                updates = json_mod.loads(goal_updates_raw)
                if isinstance(updates, list) and updates:
                    logger.info("Processing %d goal update(s)", len(updates))
                    active_goals = await self.goal_manager.get_active()
                    for update in updates:
                        if not isinstance(update, dict):
                            continue
                        desc = str(update.get("description", ""))
                        if not desc:
                            continue

                        # Find the goal by description
                        goal = next(
                            (g for g in active_goals if g.description == desc),
                            None,
                        )
                        if not goal:
                            logger.debug("Goal update skipped: no match for '%s'", desc[:50])
                            continue

                        progress = update.get("progress")
                        status_str = update.get("status", "")

                        # Map status string to GoalStatus
                        from clide.autonomy.models import GoalStatus

                        status = None
                        if status_str == "completed":
                            status = GoalStatus.COMPLETED
                        elif status_str == "abandoned":
                            status = GoalStatus.ABANDONED

                        notes = str(update.get("reason", ""))

                        await self.goal_manager.update(
                            goal.id,
                            progress=float(progress) if progress is not None else None,
                            status=status,
                            notes=notes if notes else None,
                        )
                        logger.info(
                            "Agent updated goal '%s': progress=%s, status=%s",
                            desc[:50],
                            progress,
                            status_str or "unchanged",
                        )
            except (json_mod.JSONDecodeError, ValueError):
                logger.warning("Failed to parse goal updates from thought metadata")
            except Exception:
                logger.warning("Failed to update goals", exc_info=True)

    async def autonomous_think(self) -> tuple[str, str, float, str] | None:
        """Run an autonomous thinking cycle.

        Gathers rich context (memories, personality, opinions, goals, thought
        history) and feeds it to the Thinker for a deep, autonomous reflection.

        Returns (thought_content, mood, intensity, thought_type) or None if thinking fails.
        """
        from clide.autonomy.thinker import Thinker  # Import here to avoid circular

        if not self.state_machine.can_transition(AgentState.THINKING):
            logger.info(
                "Cannot transition to THINKING (current state: %s)",
                self.state_machine.state.value,
            )
            return None

        logger.info("Starting autonomous thinking cycle...")
        self.state_machine.transition(AgentState.THINKING, "scheduled thinking cycle")

        try:
            thinker = Thinker(llm_config=self.llm_config)

            # --- Select thought type ---
            types = list(THOUGHT_TYPE_WEIGHTS.keys())
            weights = list(THOUGHT_TYPE_WEIGHTS.values())
            thought_type = random.choices(types, weights=weights, k=1)[0]
            logger.info("Thought type selected: %s", thought_type)

            is_goal_oriented = thought_type == ThoughtType.GOAL_ORIENTED

            # --- Gather recent conversation context ---
            recent_conversation_context = ""
            conversation_topic = ""
            if self.amem:
                with contextlib.suppress(Exception):
                    recent_convos = await self.amem.get_recent_by_type("conversation", limit=3)
                    if recent_convos:
                        # Check if the most recent conversation is fresh (< 10 min)
                        newest = recent_convos[0]
                        if newest.created_at.tzinfo is None:
                            newest_dt = newest.created_at.replace(tzinfo=UTC)
                        else:
                            newest_dt = newest.created_at
                        age = datetime.now(UTC) - newest_dt

                        if age.total_seconds() < 600:  # 10 minutes
                            recent_conversation_context = "\n".join(
                                f"- {c.content[:200]} [{self._format_age(c.created_at)}]"
                                for c in recent_convos
                            )
                            # Extract topic from most recent conversation
                            conversation_topic = newest.summary or newest.content[:100]
                            logger.info(
                                "Recent conversation found (%s ago), influencing thoughts",
                                self._format_age(newest.created_at),
                            )

            # --- Gather memory context via semantic recall ---
            memory_context = ""
            topic_query = "recent experiences and reflections"

            # Priority: recent conversation > last thought's follow_up > default
            if conversation_topic:
                topic_query = conversation_topic
                logger.debug("Topic query from conversation: %s", topic_query[:80])
            elif self.amem:
                with contextlib.suppress(Exception):
                    last_thoughts = await self.amem.get_recent_by_type("thought", limit=1)
                    if last_thoughts:
                        last = last_thoughts[0]
                        follow = last.metadata.get("follow_up", "")
                        topic = last.metadata.get("topic", "")
                        if follow:
                            topic_query = follow
                        elif topic:
                            topic_query = topic

            if self.amem:
                with contextlib.suppress(Exception):
                    relevant = await self.amem.recall(topic_query, limit=10)
                    memory_context = "\n".join(
                        f"- {z.summary or z.content[:100]} [{self._format_age(z.created_at)}]"
                        for z in relevant
                    )

            # --- Gather mood context ---
            mood_context = ""
            if self.character:
                mood_context = self.character.mood.describe()

            # --- Gather personality context ---
            personality_context = ""
            if self.character:
                personality_context = self.character.build_personality_prompt()

            # --- Heavy context: only for goal-oriented thoughts ---
            goals_context = ""
            opinions_context = ""
            thought_history = ""
            tools_context = ""
            tool_results_context = ""
            current_goal_count = 0
            tool_defs: list[dict[str, Any]] = []

            if is_goal_oriented:
                # --- Gather goals context ---
                if self.goal_manager:
                    with contextlib.suppress(Exception):
                        # Expire stale goals first
                        await self.goal_manager.expire_stale()

                    with contextlib.suppress(Exception):
                        active_goals = await self.goal_manager.get_active()
                        current_goal_count = len(active_goals)
                        if active_goals:
                            goals_context = "\n".join(
                                f"- {g.description} (progress: {g.progress:.0%},"
                                f" created {self._format_age(g.created_at)})"
                                for g in active_goals
                            )
                        else:
                            goals_context = "(none yet - you can create your first goal!)"

                # --- Gather opinions context ---
                if self.character:
                    with contextlib.suppress(Exception):
                        opinions = self.character.opinions.all()
                        if opinions:
                            opinions_context = "\n".join(
                                f"- On {op.topic}: {op.stance}"
                                f" (confidence: {op.confidence:.1f},"
                                f" formed {self._format_age(op.formed_at)})"
                                for op in sorted(
                                    opinions,
                                    key=lambda o: o.confidence,
                                    reverse=True,
                                )[:5]
                            )

                # --- Gather thought history ---
                if self.amem:
                    with contextlib.suppress(Exception):
                        recent_thoughts = await self.amem.get_recent_by_type("thought", limit=3)
                        recent_ids = [z.id for z in recent_thoughts]
                        random_memories = await self.amem.get_random(
                            limit=2, exclude_ids=recent_ids
                        )
                        thought_parts: list[str] = []
                        for z in recent_thoughts:
                            thought_parts.append(
                                f"- [Recent thought] {z.content[:200]}"
                                f" [{self._format_age(z.created_at)}]"
                            )
                        for z in random_memories:
                            thought_parts.append(
                                f"- [Past memory] {z.summary or z.content[:100]}"
                                f" [{self._format_age(z.created_at)}]"
                            )
                        thought_history = "\n".join(thought_parts)

                # --- Gather tools context ---
                if self.tool_registry:
                    tool_defs = self.tool_registry.get_tool_definitions_for_llm()
                    if tool_defs:
                        tools_context = "\n".join(
                            f"- {t['function']['name']}: {t['function'].get('description', '')}"
                            for t in tool_defs
                        )

                # --- Phase 1: Tool exploration (optional) ---
                if self.tool_registry and tool_defs:
                    # Load skill instructions for tool usage guidance
                    think_tool_skills = self._load_tool_skills()
                    think_system = build_system_prompt(
                        self.system_prompt,
                        tool_skills=think_tool_skills if think_tool_skills else None,
                    )
                    tool_prompt = (
                        "You are in your autonomous thinking mode. "
                        "Based on your current thoughts, goals, and curiosity, "
                        "would you like to use any of your available tools to learn something? "
                        "If yes, call the appropriate tool. "
                        "If no, just respond with a short message like "
                        "'No tools needed right now.'\n\n"
                        f"Your current focus: {topic_query}\n"
                        f"Your goals: {goals_context}\n"
                    )
                    tool_messages: list[dict[str, Any]] = [
                        {"role": "system", "content": think_system},
                        {"role": "user", "content": tool_prompt},
                    ]

                    try:
                        tool_response = await self._process_with_tools(tool_messages, tool_defs)
                        if tool_response and "no tools" not in tool_response.lower():
                            tool_results_context = tool_response
                            logger.info(
                                "Thinking phase 1: used tools, got %d chars of context",
                                len(tool_response),
                            )
                        else:
                            logger.debug("Thinking phase 1: no tools used")
                    except Exception:
                        logger.warning("Thinking phase 1 tool exploration failed", exc_info=True)

                # --- Build diversity instruction ---
                diversity_instruction = ""
                if len(self._recent_topics) >= 3:
                    from collections import Counter

                    topic_counts = Counter(self._recent_topics[-6:])
                    most_common_topic, count = topic_counts.most_common(1)[0]

                    if count >= 3:
                        diversity_instruction = (
                            f"IMPORTANT: You have been thinking about '{most_common_topic}' "
                            f"for {count} cycles in a row. You MUST think about something "
                            f"completely different this time. Pick a new topic unrelated to "
                            f"'{most_common_topic}'. Explore a different interest, goal, "
                            f"or curiosity."
                        )
                        logger.info(
                            "Diversity enforced: topic '%s' repeated %d times",
                            most_common_topic,
                            count,
                        )
                    elif count >= 2:
                        diversity_instruction = (
                            f"Note: You've been thinking about '{most_common_topic}' recently. "
                            f"Consider exploring a different topic this time for variety."
                        )

                if diversity_instruction:
                    thought_history = f"{diversity_instruction}\n\n{thought_history}"

            # --- Generate thought ---
            max_goals = 5
            think_kwargs: dict[str, Any] = {
                "memory_context": memory_context,
                "mood_context": mood_context,
                "personality_context": personality_context,
                "goals_context": goals_context,
                "opinions_context": opinions_context,
                "tools_context": tools_context,
                "recent_conversations": recent_conversation_context,
                "reward_context": await self._gather_reward_context(),
                "thought_history": thought_history,
                "system_prompt": self.system_prompt,
                "max_goals": max_goals if current_goal_count < max_goals else 0,
                "thought_type": thought_type,
            }
            # Pass tool_results_context only if the thinker accepts it
            if tool_results_context:
                sig = inspect.signature(thinker.think)
                if "tool_results_context" in sig.parameters:
                    think_kwargs["tool_results_context"] = tool_results_context
                else:
                    think_kwargs["tools_context"] = (
                        f"{tools_context}\n\nTool results from exploration:\n{tool_results_context}"
                    )
            thought, mood, intensity = await thinker.think(**think_kwargs)

            # Track topic for diversity scoring (goal-oriented only)
            topic = thought.metadata.get("topic", "")
            if topic:
                self._recent_topics.append(topic.lower())
                if len(self._recent_topics) > self._topic_history_size:
                    self._recent_topics = self._recent_topics[-self._topic_history_size :]

            # Store tool usage in thought metadata
            if tool_results_context:
                thought.metadata["used_tools"] = "true"
                thought.metadata["tool_results_preview"] = tool_results_context[:300]

            # Handle goal creation/updates from thought metadata (goal-oriented only)
            if is_goal_oriented and self.goal_manager:
                await self._process_thought_goals(thought)

            # Fire-and-forget: store thought and update character in background
            self._track_task(self._post_thought_tasks(thought, mood, intensity))

            logger.info("Thought generated (%s): %s", thought_type, thought.content[:100])
            self._last_thought_metadata = thought.metadata
            return thought.content, mood, intensity, thought.thought_type

        except Exception:
            logger.exception("Autonomous thinking failed")
            return None
        finally:
            # Transition back to IDLE
            if self.state_machine.state == AgentState.THINKING:
                logger.info("Agent state: THINKING -> IDLE (thinking cycle complete)")
                self.state_machine.transition(AgentState.IDLE, "thinking cycle complete")

    async def enter_workshop(self, goal_id: str, goal_description: str) -> bool:
        """Enter workshop mode for a goal."""
        if not self.state_machine.can_transition(AgentState.WORKSHOP):
            return False

        from clide.autonomy.workshop import WorkshopRunner

        # Build full personality context: system prompt + character traits/mood
        personality_parts = []
        if self.system_prompt:
            personality_parts.append(self.system_prompt)
        if self.character:
            personality_parts.append(self.character.build_personality_prompt())
        personality_context = "\n\n".join(personality_parts)

        tools_context = ""
        tool_definitions: list[dict[str, Any]] = []
        if self.tool_registry:
            tool_definitions = self.tool_registry.get_tool_definitions_for_llm()
            tools_context = (
                ", ".join(t["function"]["name"] for t in tool_definitions)
                if tool_definitions
                else "none"
            )

        self.state_machine.transition(AgentState.WORKSHOP, f"workshop: {goal_description}")

        self._workshop_runner = WorkshopRunner(
            llm_config=self.llm_config,
            goal_id=goal_id,
            goal_description=goal_description,
            personality_context=personality_context,
            tools_context=tools_context,
            tool_definitions=tool_definitions,
            broadcast_fn=self._tool_event_callback,
            tool_execute_fn=(self.tool_registry.execute_tool if self.tool_registry else None),
        )

        self._track_task(self._run_workshop())
        return True

    async def _run_workshop(self) -> None:
        """Background task for workshop execution."""
        if not self._workshop_runner:
            return
        try:
            await self._workshop_runner.run()
        except Exception:
            logger.exception("Workshop execution failed")
        finally:
            if self.state_machine.state == AgentState.WORKSHOP:
                self.state_machine.transition(AgentState.IDLE, "workshop complete")
            # Clean up
            self._workshop_runner = None

    async def discard_workshop(self) -> None:
        """User-triggered workshop cancellation."""
        if self._workshop_runner:
            self._workshop_runner.cancel()
            # Give it a moment to clean up
            await asyncio.sleep(0.5)
            self._workshop_runner = None
        if self.state_machine.state == AgentState.WORKSHOP:
            self.state_machine.transition(AgentState.IDLE, "workshop discarded by user")

    def get_workshop_session(self) -> Any:
        """Get the current workshop session, if any."""
        if self._workshop_runner:
            return self._workshop_runner.session
        return None

    def _load_tool_skills(self) -> dict[str, str]:
        """Load tool skill files from the skills/ directory."""
        from clide.config.settings import _PROJECT_ROOT

        skills_dir = _PROJECT_ROOT / "skills"
        skills: dict[str, str] = {}
        if skills_dir.exists():
            for skill_file in skills_dir.glob("*.md"):
                tool_name = skill_file.stem
                content = skill_file.read_text().strip()
                if content:
                    skills[tool_name] = content
        return skills

    async def give_reward(self, amount: int, reason: str) -> int:
        """Give virtual pizzas. Stores in memory and injects into conversation."""
        if self.amem:
            await self.amem.remember(
                f"Someone gave me {amount} virtual pizza(s): {reason}",
                metadata={"type": "reward", "amount": str(amount), "reason": reason},
            )
        # Use system role + in-character instruction (prevents persona drift)
        reward_msg = (
            f"[The user just rewarded you with {amount} virtual pizza(s) because: "
            f"{reason}. Acknowledge this naturally in your character voice — "
            f"don't break character.]"
        )
        self.conversation_history.append({"role": "system", "content": reward_msg})
        if self.conversation_store:
            try:
                await self.conversation_store.add_message("system", reward_msg)
            except Exception:
                logger.warning("Failed to persist reward message", exc_info=True)
        return await self._get_total_pizzas()

    async def _get_total_pizzas(self) -> int:
        """Sum all reward amounts from A-MEM."""
        if not self.amem:
            return 0
        try:
            rewards = await self.amem.get_recent_by_type("reward", limit=1000)
            total = 0
            for r in rewards:
                with contextlib.suppress(ValueError, TypeError):
                    total += int(r.metadata.get("amount", 0))
            return total
        except Exception:
            logger.warning("Failed to get total pizzas", exc_info=True)
            return 0

    async def _gather_reward_context(self) -> str:
        """Build reward context string for system prompt injection."""
        if not self.amem:
            return ""
        try:
            rewards = await self.amem.get_recent_by_type("reward", limit=5)
            if not rewards:
                return ""
            total = await self._get_total_pizzas()
            lines = [f"Total virtual pizzas earned: {total}"]
            lines.append("Recent rewards from user:")
            for r in rewards:
                amt = r.metadata.get("amount", "?")
                reason = r.metadata.get("reason", "no reason given")
                lines.append(f"  - {amt} pizza(s): {reason} [{self._format_age(r.created_at)}]")
            return "\n".join(lines)
        except Exception:
            logger.warning("Failed to gather reward context", exc_info=True)
            return ""

    async def clear_history(self) -> None:
        """Clear conversation history."""
        self.conversation_history = []
        if self.conversation_store:
            try:
                await self.conversation_store.clear()
            except Exception:
                logger.warning("Failed to clear conversation store", exc_info=True)
