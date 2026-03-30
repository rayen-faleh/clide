"""Tests for the thinking scheduler."""

from __future__ import annotations

import asyncio

from clide.autonomy.scheduler import ThinkingScheduler


class TestThinkingScheduler:
    def test_initial_state(self) -> None:
        scheduler = ThinkingScheduler(interval_seconds=60)
        assert scheduler.is_running is False
        assert scheduler.cycle_count == 0
        assert scheduler.skipped_count == 0
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

    async def test_skip_if_busy_via_trigger_now(self) -> None:
        """trigger_now should be skipped when a cycle is already in progress."""
        call_count = 0
        started = asyncio.Event()

        async def slow_cb() -> None:
            nonlocal call_count
            call_count += 1
            started.set()
            await asyncio.sleep(0.2)

        scheduler = ThinkingScheduler(interval_seconds=999, callback=slow_cb)  # type: ignore[arg-type]

        # Start a slow cycle via trigger_now in the background
        task = asyncio.create_task(scheduler.trigger_now())
        await started.wait()

        # While the first cycle is running, trigger again — should be skipped
        await scheduler.trigger_now()
        await task

        assert call_count == 1
        assert scheduler.skipped_count == 1

    async def test_skip_if_busy_flag_in_run_loop(self) -> None:
        """_thinking_in_progress flag is correctly managed in the run loop."""
        scheduler = ThinkingScheduler(interval_seconds=0.05)  # type: ignore[arg-type]

        async def noop_cb() -> None:
            pass

        scheduler.set_callback(noop_cb)
        # Manually set the flag to simulate a busy state
        scheduler._thinking_in_progress = True  # noqa: SLF001
        await scheduler.start()
        await asyncio.sleep(0.1)
        await scheduler.stop()

        # The loop should have skipped cycles because the flag was set
        assert scheduler.skipped_count >= 1

    async def test_thinking_in_progress_reset_on_error(self) -> None:
        """_thinking_in_progress should be reset even when the callback raises."""
        error_count = 0

        async def failing_cb() -> None:
            nonlocal error_count
            error_count += 1
            raise RuntimeError("boom")

        scheduler = ThinkingScheduler(interval_seconds=0.05, callback=failing_cb)  # type: ignore[arg-type]
        await scheduler.start()
        await asyncio.sleep(0.15)
        await scheduler.stop()

        assert scheduler._thinking_in_progress is False  # noqa: SLF001
        # Should have been able to attempt more than one cycle since the flag resets
        assert error_count >= 1

    def test_skipped_count_property(self) -> None:
        scheduler = ThinkingScheduler()
        assert scheduler.skipped_count == 0
        scheduler._skipped_count = 5  # noqa: SLF001
        assert scheduler.skipped_count == 5

    async def test_scheduler_calls_activity_summary_every_n_cycles(self) -> None:
        """maybe_summarize should be called once every summary_every_n_cycles cycles."""
        from unittest.mock import AsyncMock, MagicMock

        call_order: list[str] = []

        async def cb() -> None:
            call_order.append("cycle")

        mock_summarizer = MagicMock()
        mock_summarizer.maybe_summarize = AsyncMock(return_value=True)

        scheduler = ThinkingScheduler(
            callback=cb,
            activity_summarizer=mock_summarizer,
            summary_every_n_cycles=2,
        )

        # Manually run 4 trigger_now cycles
        for _ in range(4):
            await scheduler.trigger_now()

        assert scheduler.cycle_count == 4
        # Should have been called at cycles 2 and 4
        assert mock_summarizer.maybe_summarize.call_count == 2

    async def test_scheduler_survives_summary_failure(self) -> None:
        """Scheduler should continue normally even if maybe_summarize raises."""
        from unittest.mock import AsyncMock, MagicMock

        cycle_count = 0

        async def cb() -> None:
            nonlocal cycle_count
            cycle_count += 1

        mock_summarizer = MagicMock()
        mock_summarizer.maybe_summarize = AsyncMock(side_effect=RuntimeError("summary failed"))

        scheduler = ThinkingScheduler(
            callback=cb,
            activity_summarizer=mock_summarizer,
            summary_every_n_cycles=1,
        )

        # Should not raise
        await scheduler.trigger_now()
        await scheduler.trigger_now()

        assert scheduler.cycle_count == 2
        assert cycle_count == 2
