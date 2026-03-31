"""Periodic cross-mode activity summarizer."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from clide.core.context_builder import _format_event
from clide.core.llm import LLMConfig, stream_completion

if TYPE_CHECKING:
    from clide.core.event_log import EventLog
    from clide.memory.amem import AMem

logger = logging.getLogger(__name__)

_DIGEST_MAX_CHARS = 2000


class ActivitySummarizer:
    """Periodically generates a first-person journal entry summarizing cross-mode activity."""

    def __init__(
        self,
        event_log: EventLog,
        amem: AMem,
        llm_config: LLMConfig,
        agent_name: str = "Clide",
        min_events_threshold: int = 5,
    ) -> None:
        self._event_log = event_log
        self._amem = amem
        self._llm_config = llm_config
        self._agent_name = agent_name
        self._min_events_threshold = min_events_threshold
        self._last_summary_at: str | None = None

    async def maybe_summarize(self) -> bool:
        """Generate activity summary if enough events have occurred.

        Returns True if a summary was created, False otherwise.
        """
        now = datetime.now(UTC)

        # 1. Determine lookback timestamp
        since = await self._resolve_since(now)

        # 2. Gate on event count
        count = await self._event_log.count_since(since)
        if count < self._min_events_threshold:
            logger.debug(
                "ActivitySummarizer: only %d events since %s (threshold %d), skipping",
                count,
                since,
                self._min_events_threshold,
            )
            return False

        # 3. Fetch events
        events = await self._event_log.get_since(since, limit=100)

        # 4. Build digest
        digest = self._build_digest(events)

        # 5. LLM call
        try:
            summary = await self._generate_summary(digest)
        except Exception:
            logger.warning("ActivitySummarizer: LLM call failed", exc_info=True)
            return False

        # 6. Store in A-MEM
        await self._amem.remember(
            f"{self._agent_name}'s activity journal: {summary}",
            metadata={
                "type": "activity_summary",
                "events_covered": str(count),
                "period_start": since,
                "period_end": now.isoformat(),
            },
        )

        # 7. Prune old events (piggyback on periodic summary)
        try:
            pruned = await self._event_log.prune(max_age_days=7)
            if pruned:
                logger.info("ActivitySummarizer: pruned %d old events", pruned)
        except Exception:
            logger.warning("EventLog prune failed", exc_info=True)

        # 8. Update last summary timestamp
        self._last_summary_at = now.isoformat()
        logger.info("ActivitySummarizer: created summary covering %d events", count)
        return True

    async def _resolve_since(self, now: datetime) -> str:
        """Resolve the lookback timestamp."""
        if self._last_summary_at is not None:
            return self._last_summary_at

        # Query A-MEM for the most recent activity summary
        try:
            recent = await self._amem.get_recent_by_type("activity_summary", limit=1)
            if recent:
                entry = recent[0]
                created_at: Any = getattr(entry, "created_at", None)
                if created_at is not None:
                    if isinstance(created_at, datetime):
                        return created_at.isoformat()
                    return str(created_at)
        except Exception:
            logger.warning(
                "ActivitySummarizer: could not query amem for last summary", exc_info=True
            )

        # Default: 1 hour ago
        return (now - timedelta(hours=1)).isoformat()

    def _build_digest(self, events: list[dict[str, Any]]) -> str:
        """Format events into a digest string, truncated to _DIGEST_MAX_CHARS."""
        lines: list[str] = []
        for event in events:
            line = _format_event(event)
            if line:
                lines.append(line)

        digest = "\n".join(lines)
        if len(digest) > _DIGEST_MAX_CHARS:
            digest = digest[:_DIGEST_MAX_CHARS]
        return digest

    async def _generate_summary(self, digest: str) -> str:
        """Call the LLM to generate a journal entry from the digest."""
        prompt = (
            f"You are {self._agent_name}. Write a brief first-person journal entry summarizing "
            "what you've been doing recently. Be reflective and concise (3-6 sentences). "
            "Focus on what matters most.\n\n"
            f"Recent activity:\n{digest}\n\n"
            "Journal entry:"
        )
        messages: list[dict[str, str]] = [{"role": "user", "content": prompt}]

        tokens: list[str] = []
        async for token in stream_completion(messages, self._llm_config):
            tokens.append(token)

        return "".join(tokens).strip()
