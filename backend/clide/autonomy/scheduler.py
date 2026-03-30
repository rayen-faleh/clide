"""Scheduled thinking loop for autonomous agent behavior."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable, Coroutine
from typing import Any

logger = logging.getLogger(__name__)


class ThinkingScheduler:
    """Manages the periodic autonomous thinking cycle.

    Uses simple asyncio task scheduling (APScheduler can be added later
    for more complex scheduling needs).
    """

    def __init__(
        self,
        interval_seconds: float = 300,
        callback: Callable[[], Coroutine[Any, Any, None]] | None = None,
        agent_state_fn: Callable[[], Any] | None = None,
        activity_summarizer: Any = None,
        summary_every_n_cycles: int = 5,
    ) -> None:
        self.interval_seconds = interval_seconds
        self._callback = callback
        self._agent_state_fn = agent_state_fn
        self._activity_summarizer = activity_summarizer
        self._summary_every_n_cycles = summary_every_n_cycles
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._paused = False
        self._cycle_count = 0
        self._thinking_in_progress = False
        self._skipped_count = 0

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_paused(self) -> bool:
        return self._paused

    def pause(self) -> None:
        """Pause the thinking scheduler (keeps running but skips cycles)."""
        self._paused = True
        logger.info("Thinking scheduler paused")

    def resume(self) -> None:
        """Resume the thinking scheduler."""
        self._paused = False
        logger.info("Thinking scheduler resumed")

    @property
    def cycle_count(self) -> int:
        return self._cycle_count

    @property
    def skipped_count(self) -> int:
        return self._skipped_count

    def set_callback(self, callback: Callable[[], Coroutine[Any, Any, None]]) -> None:
        """Set the callback to run on each thinking cycle."""
        self._callback = callback

    async def start(self) -> None:
        """Start the thinking loop."""
        if self._running:
            return

        if not self._callback:
            logger.warning("No callback set for thinking scheduler")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Thinking scheduler started (interval: %ss)", self.interval_seconds)

    async def stop(self) -> None:
        """Stop the thinking loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        logger.info("Thinking scheduler stopped")

    async def trigger_now(self) -> None:
        """Trigger an immediate thinking cycle (skipped if one is already running)."""
        if not self._callback:
            return
        if self._thinking_in_progress:
            logger.info("Skipping manual trigger - thinking cycle already in progress")
            self._skipped_count += 1
            return
        self._thinking_in_progress = True
        try:
            await self._callback()
            self._cycle_count += 1
            # Periodic activity summary
            if (
                self._activity_summarizer is not None
                and self._cycle_count % self._summary_every_n_cycles == 0
            ):
                try:
                    await self._activity_summarizer.maybe_summarize()
                except Exception:
                    logger.warning("Activity summary failed", exc_info=True)
        finally:
            self._thinking_in_progress = False

    async def _run_loop(self) -> None:
        """Main loop that fires the callback at intervals."""
        while self._running:
            try:
                # Check if paused
                if self._paused:
                    await asyncio.sleep(self.interval_seconds)
                    continue

                # Check if agent is in workshop mode
                if self._agent_state_fn:
                    current_state = self._agent_state_fn()
                    if str(current_state) == "workshop":
                        logger.info("Skipping thinking cycle - agent in workshop mode")
                        self._skipped_count += 1
                        await asyncio.sleep(self.interval_seconds)
                        continue

                if self._running and self._callback:
                    if self._thinking_in_progress:
                        logger.info("Skipping thinking cycle - previous cycle still in progress")
                        self._skipped_count += 1
                    else:
                        self._thinking_in_progress = True
                        try:
                            logger.info("Thinking cycle #%d starting...", self._cycle_count + 1)
                            await self._callback()
                            self._cycle_count += 1
                            logger.info("Thinking cycle #%d complete", self._cycle_count)
                            # Periodic activity summary
                            if (
                                self._activity_summarizer is not None
                                and self._cycle_count % self._summary_every_n_cycles == 0
                            ):
                                try:
                                    await self._activity_summarizer.maybe_summarize()
                                except Exception:
                                    logger.warning("Activity summary failed", exc_info=True)
                        finally:
                            self._thinking_in_progress = False
                await asyncio.sleep(self.interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in thinking cycle")
                self._thinking_in_progress = False
                await asyncio.sleep(self.interval_seconds)  # Back off on error
