"""Token and cost tracking for LLM usage."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum

logger = logging.getLogger(__name__)


class UsagePurpose(StrEnum):
    """Purpose of an LLM call for cost tracking."""

    CHAT = "chat"
    AUTONOMOUS = "autonomous"
    MEMORY_PROCESSING = "memory_processing"
    TOOL_USE = "tool_use"


@dataclass
class TokenUsage:
    """Token usage for a single LLM call."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    purpose: UsagePurpose = UsagePurpose.CHAT
    model: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class DailyUsage:
    """Aggregated usage for a single day."""

    date: date
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    call_count: int = 0
    by_purpose: dict[str, int] = field(default_factory=dict)


class CostTracker:
    """Tracks token usage and enforces budget limits."""

    def __init__(
        self,
        daily_token_limit: int = 500_000,
        warning_threshold: float = 0.8,
    ) -> None:
        self.daily_token_limit = daily_token_limit
        self.warning_threshold = warning_threshold
        self._usage_log: list[TokenUsage] = []

    def record(self, usage: TokenUsage) -> None:
        """Record a token usage entry."""
        self._usage_log.append(usage)

        # Check budget
        today_usage = self.get_daily_usage()
        if today_usage.total_tokens >= self.daily_token_limit:
            logger.warning(
                "Daily token budget EXHAUSTED: %d/%d",
                today_usage.total_tokens,
                self.daily_token_limit,
            )
        elif today_usage.total_tokens >= self.daily_token_limit * self.warning_threshold:
            logger.warning(
                "Daily token budget warning: %d/%d (%.0f%%)",
                today_usage.total_tokens,
                self.daily_token_limit,
                today_usage.total_tokens / self.daily_token_limit * 100,
            )

    def get_daily_usage(self, target_date: date | None = None) -> DailyUsage:
        """Get aggregated usage for a specific day (defaults to today)."""
        target = target_date or datetime.now(UTC).date()
        daily = DailyUsage(date=target)

        for entry in self._usage_log:
            if entry.timestamp.date() == target:
                daily.total_tokens += entry.total_tokens
                daily.prompt_tokens += entry.prompt_tokens
                daily.completion_tokens += entry.completion_tokens
                daily.call_count += 1
                purpose_key = entry.purpose.value
                daily.by_purpose[purpose_key] = (
                    daily.by_purpose.get(purpose_key, 0) + entry.total_tokens
                )

        return daily

    def is_budget_exhausted(self) -> bool:
        """Check if the daily budget is exhausted."""
        return self.get_daily_usage().total_tokens >= self.daily_token_limit

    def is_budget_warning(self) -> bool:
        """Check if usage has crossed the warning threshold."""
        usage = self.get_daily_usage()
        return usage.total_tokens >= self.daily_token_limit * self.warning_threshold

    def get_budget_remaining(self) -> int:
        """Get remaining tokens in the daily budget."""
        usage = self.get_daily_usage()
        return max(0, self.daily_token_limit - usage.total_tokens)

    def get_usage_percentage(self) -> float:
        """Get current usage as a percentage of daily limit."""
        usage = self.get_daily_usage()
        if self.daily_token_limit == 0:
            return 100.0
        return (usage.total_tokens / self.daily_token_limit) * 100

    def get_stats(self) -> dict[str, object]:
        """Get comprehensive usage stats for the API."""
        daily = self.get_daily_usage()
        return {
            "daily": {
                "date": daily.date.isoformat(),
                "total_tokens": daily.total_tokens,
                "prompt_tokens": daily.prompt_tokens,
                "completion_tokens": daily.completion_tokens,
                "call_count": daily.call_count,
                "by_purpose": daily.by_purpose,
            },
            "budget": {
                "daily_limit": self.daily_token_limit,
                "remaining": self.get_budget_remaining(),
                "usage_percentage": round(self.get_usage_percentage(), 1),
                "exhausted": self.is_budget_exhausted(),
                "warning": self.is_budget_warning(),
            },
        }

    def clear(self) -> None:
        """Clear all usage records."""
        self._usage_log.clear()
