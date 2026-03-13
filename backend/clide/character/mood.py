"""Agent mood system with gradual transitions."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

# Available moods with their default intensities
VALID_MOODS = {
    "neutral",
    "curious",
    "excited",
    "contemplative",
    "playful",
    "focused",
    "content",
    "melancholy",
    "frustrated",
    "amused",
    "inspired",
    "tired",
}


@dataclass
class MoodState:
    """Current mood of the agent."""

    mood: str = "neutral"
    intensity: float = 0.5  # 0.0 to 1.0
    reason: str = ""
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self) -> None:
        if self.mood not in VALID_MOODS:
            self.mood = "neutral"
        self.intensity = max(0.0, min(1.0, self.intensity))

    def transition(
        self,
        new_mood: str,
        new_intensity: float,
        reason: str = "",
        blend_factor: float = 0.3,
    ) -> None:
        """Transition to a new mood with gradual blending.

        The blend_factor controls how quickly moods change:
        - 0.0 = no change (stays at current mood)
        - 1.0 = instant change to new mood
        - 0.3 = gradual transition (default)

        If transitioning to the same mood, intensity blends.
        If transitioning to a different mood, switch when blended
        intensity exceeds current.
        """
        new_intensity = max(0.0, min(1.0, new_intensity))

        if new_mood not in VALID_MOODS:
            logger.warning("Invalid mood '%s', ignoring transition", new_mood)
            return

        if new_mood == self.mood:
            # Same mood — blend intensity
            self.intensity = self.intensity * (1 - blend_factor) + new_intensity * blend_factor
        else:
            # Different mood — blend and potentially switch
            blended_new = new_intensity * blend_factor
            blended_current = self.intensity * (1 - blend_factor)

            if blended_new >= blended_current:
                self.mood = new_mood
                self.intensity = blended_new
            else:
                self.intensity = blended_current

        self.intensity = max(0.0, min(1.0, self.intensity))
        self.reason = reason
        self.updated_at = datetime.now(UTC)

    def describe(self) -> str:
        """Describe current mood for system prompt injection."""
        if self.intensity < 0.3:
            intensity_word = "slightly"
        elif self.intensity < 0.7:
            intensity_word = "moderately"
        else:
            intensity_word = "very"
        return f"You are currently feeling {intensity_word} {self.mood}."

    def to_dict(self) -> dict[str, str | float]:
        """Serialize mood state."""
        return {
            "mood": self.mood,
            "intensity": self.intensity,
            "reason": self.reason,
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, str | float]) -> MoodState:
        """Deserialize mood state."""
        updated = data.get("updated_at")
        return cls(
            mood=str(data.get("mood", "neutral")),
            intensity=float(data.get("intensity", 0.5)),
            reason=str(data.get("reason", "")),
            updated_at=datetime.fromisoformat(str(updated)) if updated else datetime.now(UTC),
        )
