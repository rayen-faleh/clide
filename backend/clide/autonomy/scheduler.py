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
    ) -> None:
        self.interval_seconds = interval_seconds
        self._callback = callback
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._cycle_count = 0

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def cycle_count(self) -> int:
        return self._cycle_count

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
        """Trigger an immediate thinking cycle."""
        if self._callback:
            await self._callback()
            self._cycle_count += 1

    async def _run_loop(self) -> None:
        """Main loop that fires the callback at intervals."""
        while self._running:
            try:
                if self._running and self._callback:
                    await self._callback()
                    self._cycle_count += 1
                await asyncio.sleep(self.interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in thinking cycle")
                await asyncio.sleep(self.interval_seconds)  # Back off on error
