"""Tests for scheduler workshop mode skip behavior."""

from __future__ import annotations

import asyncio

from clide.api.schemas import AgentState
from clide.autonomy.scheduler import ThinkingScheduler


class TestSchedulerWorkshopSkip:
    """Tests that the scheduler skips thinking cycles during workshop mode."""

    async def test_skips_when_in_workshop_state(self) -> None:
        call_count = 0

        async def cb() -> None:
            nonlocal call_count
            call_count += 1

        scheduler = ThinkingScheduler(
            interval_seconds=0.05,  # type: ignore[arg-type]
            callback=cb,
            agent_state_fn=lambda: AgentState.WORKSHOP,
        )
        await scheduler.start()
        await asyncio.sleep(0.15)
        await scheduler.stop()

        # Should have skipped all cycles
        assert call_count == 0
        assert scheduler.skipped_count >= 1

    async def test_runs_when_not_in_workshop(self) -> None:
        call_count = 0

        async def cb() -> None:
            nonlocal call_count
            call_count += 1

        scheduler = ThinkingScheduler(
            interval_seconds=0.05,  # type: ignore[arg-type]
            callback=cb,
            agent_state_fn=lambda: AgentState.IDLE,
        )
        await scheduler.start()
        await asyncio.sleep(0.15)
        await scheduler.stop()

        # Should have run at least one cycle
        assert call_count >= 1

    async def test_runs_without_state_fn(self) -> None:
        call_count = 0

        async def cb() -> None:
            nonlocal call_count
            call_count += 1

        scheduler = ThinkingScheduler(
            interval_seconds=0.05,  # type: ignore[arg-type]
            callback=cb,
        )
        await scheduler.start()
        await asyncio.sleep(0.15)
        await scheduler.stop()

        # Without state function, should run normally
        assert call_count >= 1

    async def test_resumes_after_workshop_ends(self) -> None:
        call_count = 0
        current_state = AgentState.WORKSHOP

        async def cb() -> None:
            nonlocal call_count
            call_count += 1

        scheduler = ThinkingScheduler(
            interval_seconds=0.05,  # type: ignore[arg-type]
            callback=cb,
            agent_state_fn=lambda: current_state,
        )
        await scheduler.start()

        # Workshop mode - should skip
        await asyncio.sleep(0.1)
        skipped_during_workshop = scheduler.skipped_count
        assert skipped_during_workshop >= 1
        assert call_count == 0

        # End workshop - should resume
        current_state = AgentState.IDLE
        await asyncio.sleep(0.15)
        await scheduler.stop()

        assert call_count >= 1

    def test_init_with_state_fn(self) -> None:
        def state_fn() -> AgentState:
            return AgentState.IDLE

        scheduler = ThinkingScheduler(
            interval_seconds=60,
            agent_state_fn=state_fn,
        )
        assert scheduler._agent_state_fn is state_fn  # noqa: SLF001
