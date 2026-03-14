"""Tests for token/cost tracking."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from clide.core.cost import CostTracker, DailyUsage, TokenUsage, UsagePurpose


class TestTokenUsage:
    def test_defaults(self) -> None:
        usage = TokenUsage()
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0
        assert usage.total_tokens == 0
        assert usage.purpose == UsagePurpose.CHAT
        assert usage.model == ""


class TestCostTracker:
    def test_record_usage(self) -> None:
        tracker = CostTracker()
        usage = TokenUsage(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            purpose=UsagePurpose.CHAT,
            model="test-model",
        )
        tracker.record(usage)
        daily = tracker.get_daily_usage()
        assert daily.total_tokens == 150
        assert daily.call_count == 1

    def test_get_daily_usage_aggregates(self) -> None:
        tracker = CostTracker()
        tracker.record(TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150))
        tracker.record(TokenUsage(prompt_tokens=200, completion_tokens=100, total_tokens=300))
        daily = tracker.get_daily_usage()
        assert daily.total_tokens == 450
        assert daily.prompt_tokens == 300
        assert daily.completion_tokens == 150
        assert daily.call_count == 2

    def test_get_daily_usage_by_purpose(self) -> None:
        tracker = CostTracker()
        tracker.record(TokenUsage(total_tokens=100, purpose=UsagePurpose.CHAT))
        tracker.record(TokenUsage(total_tokens=200, purpose=UsagePurpose.AUTONOMOUS))
        tracker.record(TokenUsage(total_tokens=50, purpose=UsagePurpose.CHAT))
        daily = tracker.get_daily_usage()
        assert daily.by_purpose["chat"] == 150
        assert daily.by_purpose["autonomous"] == 200

    def test_is_budget_exhausted(self) -> None:
        tracker = CostTracker(daily_token_limit=1000)
        tracker.record(TokenUsage(total_tokens=1000))
        assert tracker.is_budget_exhausted() is True

    def test_is_budget_not_exhausted(self) -> None:
        tracker = CostTracker(daily_token_limit=1000)
        tracker.record(TokenUsage(total_tokens=500))
        assert tracker.is_budget_exhausted() is False

    def test_is_budget_warning(self) -> None:
        tracker = CostTracker(daily_token_limit=1000, warning_threshold=0.8)
        tracker.record(TokenUsage(total_tokens=800))
        assert tracker.is_budget_warning() is True

    def test_is_budget_no_warning_below_threshold(self) -> None:
        tracker = CostTracker(daily_token_limit=1000, warning_threshold=0.8)
        tracker.record(TokenUsage(total_tokens=700))
        assert tracker.is_budget_warning() is False

    def test_get_budget_remaining(self) -> None:
        tracker = CostTracker(daily_token_limit=1000)
        tracker.record(TokenUsage(total_tokens=300))
        assert tracker.get_budget_remaining() == 700

    def test_get_budget_remaining_never_negative(self) -> None:
        tracker = CostTracker(daily_token_limit=1000)
        tracker.record(TokenUsage(total_tokens=1500))
        assert tracker.get_budget_remaining() == 0

    def test_get_usage_percentage(self) -> None:
        tracker = CostTracker(daily_token_limit=1000)
        tracker.record(TokenUsage(total_tokens=250))
        assert tracker.get_usage_percentage() == 25.0

    def test_get_usage_percentage_zero_limit(self) -> None:
        tracker = CostTracker(daily_token_limit=0)
        assert tracker.get_usage_percentage() == 100.0

    def test_get_stats_format(self) -> None:
        tracker = CostTracker(daily_token_limit=10000)
        tracker.record(
            TokenUsage(
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
                purpose=UsagePurpose.MEMORY_PROCESSING,
            )
        )
        stats = tracker.get_stats()
        assert "daily" in stats
        assert "budget" in stats
        assert stats["daily"]["date"] == datetime.now(UTC).date().isoformat()
        assert stats["daily"]["total_tokens"] == 150
        assert stats["daily"]["prompt_tokens"] == 100
        assert stats["daily"]["completion_tokens"] == 50
        assert stats["daily"]["call_count"] == 1
        assert stats["daily"]["by_purpose"]["memory_processing"] == 150
        assert stats["budget"]["daily_limit"] == 10000
        assert stats["budget"]["remaining"] == 9850
        assert stats["budget"]["usage_percentage"] == 1.5
        assert stats["budget"]["exhausted"] is False
        assert stats["budget"]["warning"] is False

    def test_clear_resets(self) -> None:
        tracker = CostTracker()
        tracker.record(TokenUsage(total_tokens=500))
        tracker.clear()
        daily = tracker.get_daily_usage()
        assert daily.total_tokens == 0
        assert daily.call_count == 0

    def test_different_days_separate(self) -> None:
        tracker = CostTracker()
        today = datetime.now(UTC)
        yesterday = today - timedelta(days=1)
        tracker.record(TokenUsage(total_tokens=100, timestamp=today))
        tracker.record(TokenUsage(total_tokens=200, timestamp=yesterday))

        today_usage = tracker.get_daily_usage(target_date=today.date())
        yesterday_usage = tracker.get_daily_usage(target_date=yesterday.date())
        assert today_usage.total_tokens == 100
        assert yesterday_usage.total_tokens == 200


class TestDailyUsage:
    def test_defaults(self) -> None:
        daily = DailyUsage(date=date.today())
        assert daily.total_tokens == 0
        assert daily.call_count == 0
        assert daily.by_purpose == {}
