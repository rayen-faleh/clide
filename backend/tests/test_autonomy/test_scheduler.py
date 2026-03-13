"""Tests for the thinking scheduler."""

from __future__ import annotations

import asyncio

from clide.autonomy.scheduler import ThinkingScheduler


class TestThinkingScheduler:
    def test_initial_state(self) -> None:
        scheduler = ThinkingScheduler(interval_seconds=60)
        assert scheduler.is_running is False
        assert scheduler.cycle_count == 0
        assert scheduler.interval_seconds == 60

    def test_set_callback(self) -> None:
        scheduler = ThinkingScheduler()

        async def cb() -> None:
            pass

        scheduler.set_callback(cb)
        assert scheduler._callback is cb  # noqa: SLF001

    async def test_trigger_now_calls_callback(self) -> None:
        call_count = 0

        async def cb() -> None:
            nonlocal call_count
            call_count += 1

        scheduler = ThinkingScheduler(callback=cb)
        await scheduler.trigger_now()
        assert call_count == 1
        assert scheduler.cycle_count == 1

    async def test_trigger_now_without_callback(self) -> None:
        scheduler = ThinkingScheduler()
        # Should not raise
        await scheduler.trigger_now()
        assert scheduler.cycle_count == 0

    async def test_start_and_stop(self) -> None:
        call_count = 0

        async def cb() -> None:
            nonlocal call_count
            call_count += 1

        scheduler = ThinkingScheduler(interval_seconds=0.05, callback=cb)  # type: ignore[arg-type]
        await scheduler.start()
        assert scheduler.is_running is True

        # First callback fires immediately, then sleeps; wait enough for at least one cycle
        await asyncio.sleep(0.1)
        await scheduler.stop()
        assert scheduler.is_running is False
        assert call_count >= 1

    async def test_cycle_count_increments(self) -> None:
        call_count = 0

        async def cb() -> None:
            nonlocal call_count
            call_count += 1

        scheduler = ThinkingScheduler(interval_seconds=0.05, callback=cb)  # type: ignore[arg-type]
        await scheduler.start()
        await asyncio.sleep(0.2)
        await scheduler.stop()
        assert scheduler.cycle_count >= 2

    async def test_start_no_callback_does_nothing(self) -> None:
        scheduler = ThinkingScheduler()
        await scheduler.start()
        assert scheduler.is_running is False

    async def test_double_start_ignored(self) -> None:
        async def cb() -> None:
            pass

        scheduler = ThinkingScheduler(interval_seconds=1, callback=cb)
        await scheduler.start()
        await scheduler.start()  # Should not create a second task
        assert scheduler.is_running is True
        await scheduler.stop()
