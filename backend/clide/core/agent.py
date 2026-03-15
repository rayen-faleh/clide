"""Core agent implementation."""

from __future__ import annotations

import asyncio
import contextlib
import json as json_mod
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from clide.api.schemas import AgentState
from clide.core.llm import LLMConfig, complete_with_tools, stream_completion
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

    async def _process_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> str:
        """Execute the agentic tool loop.

        Calls LLM with tools. If LLM requests tool calls, executes them
        via MCP registry, feeds results back, and loops until LLM produces
        a text response.

        Returns the final text response.
        """
        max_iterations = 10

        for iteration in range(max_iterations):
            logger.info("Tool loop iteration %d/%d", iteration + 1, max_iterations)
            response = await complete_with_tools(messages, self.llm_config, tools)
            choice = response.choices[0]
            logger.debug(
                "LLM response: finish_reason=%s, has_tool_calls=%s, has_content=%s",
                choice.finish_reason,
                bool(choice.message.tool_calls) if hasattr(choice.message, "tool_calls") else "N/A",
                bool(choice.message.content),
            )

            # Check if LLM wants to call tools
            if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
                logger.info("LLM requested %d tool call(s)", len(choice.message.tool_calls))

                # Transition to WORKING
                if self.state_machine.can_transition(AgentState.WORKING):
                    self.state_machine.transition(AgentState.WORKING, "tool call")

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

                    logger.info("Executing tool: %s(args=%s)", tool_name, str(arguments)[:200])

                    # Execute via registry
                    assert self.tool_registry is not None
                    result = await self.tool_registry.execute_tool(tool_name, arguments)

                    logger.info(
                        "Tool %s result: success=%s, result_preview=%s",
                        tool_name,
                        result.success,
                        str(result.result)[:150] if result.success else f"ERROR: {result.error}",
                    )

                    # Notify callback (WebSocket handler broadcasts this)
                    if self._tool_event_callback:
                        try:
                            await self._tool_event_callback(
                                {
                                    "tool_name": tool_name,
                                    "arguments": arguments,
                                    "call_id": call_id,
                                    "result": result.result if result.success else None,
                                    "error": result.error if not result.success else None,
                                    "success": result.success,
                                }
                            )
                        except Exception:
                            logger.warning("Tool event callback failed", exc_info=True)

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

                # Transition back to CONVERSING
                if self.state_machine.state == AgentState.WORKING:
                    self.state_machine.transition(AgentState.CONVERSING, "tool results ready")

                # Loop: call LLM again with tool results
                continue

            else:
                # LLM generated text response (no more tool calls)
                text = choice.message.content or ""
                logger.info(
                    "Tool loop done: %d iteration(s), %d chars",
                    iteration + 1,
                    len(text),
                )
                return text

        # Safety: too many iterations
        logger.warning("Tool loop hit max iterations (%d)", max_iterations)
        return "I got caught in a tool loop. Let me try a different approach."

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

        system = build_system_prompt(
            self.system_prompt,
            personality_additions=personality,
            memory_context=memory_context,
            agent_born_at=self.born_at,
        )

        # Build messages for LLM
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            *self.conversation_history,
        ]

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
            full_response = await self._process_with_tools(messages, tool_definitions)
            yield full_response
        else:
            # SIMPLE PATH: streaming without tools (existing behavior)
            logger.info("Streaming LLM response (no tools)...")
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

        # Trim history if needed
        if len(self.conversation_history) > self._max_history_length:
            self.conversation_history = self.conversation_history[-self._max_history_length :]

        # Transition back to IDLE immediately (don't block on memory/character)
        if self.state_machine.state == AgentState.CONVERSING:
            logger.info("Agent state: CONVERSING -> IDLE (response complete)")
            self.state_machine.transition(AgentState.IDLE, "response complete")

        # Fire-and-forget: store memory and update character in background
        logger.debug("Storing conversation to memory (background)")
        asyncio.create_task(self._post_response_tasks(content, full_response))

    async def _post_response_tasks(self, content: str, full_response: str) -> None:
        """Background tasks after response: store memory and update character."""
        if self.amem:
            try:
                await self.amem.remember(
                    f"User said: {content}\nClide responded: {full_response[:500]}",
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
                    f"Autonomous thought: {getattr(thought, 'content', str(thought))}",
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

    async def autonomous_think(self) -> tuple[str, str, float] | None:
        """Run an autonomous thinking cycle.

        Gathers rich context (memories, personality, opinions, goals, thought
        history) and feeds it to the Thinker for a deep, autonomous reflection.

        Returns (thought_content, mood, intensity) or None if thinking fails.
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

            # --- Gather memory context via semantic recall ---
            memory_context = ""
            topic_query = "recent experiences and reflections"
            if self.amem:
                # Try to find the last thought's follow_up or topic for continuity
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

            # --- Gather goals context ---
            goals_context = ""
            current_goal_count = 0
            if self.goal_manager:
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
            opinions_context = ""
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
            thought_history = ""
            if self.amem:
                with contextlib.suppress(Exception):
                    # Get the 3 most recent thoughts directly from SQLite (guaranteed fresh)
                    recent_thoughts = await self.amem.get_recent_by_type("thought", limit=3)
                    recent_ids = [z.id for z in recent_thoughts]

                    # Get 2 random memories for variety (exclude recent thoughts)
                    random_memories = await self.amem.get_random(limit=2, exclude_ids=recent_ids)

                    # Format with timestamps
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
            tools_context = ""
            if self.tool_registry:
                tool_defs = self.tool_registry.get_tool_definitions_for_llm()
                if tool_defs:
                    tools_context = "\n".join(
                        f"- {t['function']['name']}: {t['function'].get('description', '')}"
                        for t in tool_defs
                    )

            # --- Think ---
            max_goals = 5
            thought, mood, intensity = await thinker.think(
                memory_context=memory_context,
                mood_context=mood_context,
                personality_context=personality_context,
                goals_context=goals_context,
                opinions_context=opinions_context,
                tools_context=tools_context,
                thought_history=thought_history,
                system_prompt=self.system_prompt,
                max_goals=max_goals if current_goal_count < max_goals else 0,
            )

            # Handle goal creation/updates from thought metadata
            if self.goal_manager:
                await self._process_thought_goals(thought)

            # Fire-and-forget: store thought and update character in background
            asyncio.create_task(self._post_thought_tasks(thought, mood, intensity))

            logger.info("Thought generated: %s", thought.content[:100])
            return thought.content, mood, intensity

        except Exception:
            logger.exception("Autonomous thinking failed")
            return None
        finally:
            # Transition back to IDLE
            if self.state_machine.state == AgentState.THINKING:
                logger.info("Agent state: THINKING -> IDLE (thinking cycle complete)")
                self.state_machine.transition(AgentState.IDLE, "thinking cycle complete")

    async def clear_history(self) -> None:
        """Clear conversation history."""
        self.conversation_history = []
        if self.conversation_store:
            try:
                await self.conversation_store.clear()
            except Exception:
                logger.warning("Failed to clear conversation store", exc_info=True)
