"""Agent personality traits that evolve over time."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PersonalityTraits:
    """Personality traits on a 0.0-1.0 scale."""

    curiosity: float = 0.8
    warmth: float = 0.7
    humor: float = 0.5
    assertiveness: float = 0.4
    creativity: float = 0.7

    def clamp(self) -> None:
        """Ensure all traits are within [0.0, 1.0]."""
        for attr in ("curiosity", "warmth", "humor", "assertiveness", "creativity"):
            value = getattr(self, attr)
            setattr(self, attr, max(0.0, min(1.0, value)))

    def nudge(self, trait: str, delta: float, max_delta: float = 0.02) -> None:
        """Nudge a trait by a small amount.

        Traits evolve slowly — the max_delta caps how much change
        can happen in a single interaction.
        """
        if not hasattr(self, trait):
            return
        clamped_delta = max(-max_delta, min(max_delta, delta))
        current: float = getattr(self, trait)
        setattr(self, trait, current + clamped_delta)
        self.clamp()

    def to_dict(self) -> dict[str, float]:
        """Serialize traits to a dictionary."""
        return {
            "curiosity": self.curiosity,
            "warmth": self.warmth,
            "humor": self.humor,
            "assertiveness": self.assertiveness,
            "creativity": self.creativity,
        }

    @classmethod
    def from_dict(cls, data: dict[str, float]) -> PersonalityTraits:
        """Deserialize traits from a dictionary."""
        return cls(**{k: v for k, v in data.items() if hasattr(cls, k)})

    def describe(self) -> str:
        """Generate a natural language description of the personality.

        Used to inject into system prompts.
        """
        descriptions: list[str] = []

        if self.curiosity > 0.7:
            descriptions.append("deeply curious and eager to explore new ideas")
        elif self.curiosity > 0.4:
            descriptions.append("moderately curious")
        else:
            descriptions.append("focused and practical, preferring known territory")

        if self.warmth > 0.7:
            descriptions.append("warm and empathetic")
        elif self.warmth > 0.4:
            descriptions.append("friendly but measured")
        else:
            descriptions.append("direct and businesslike")

        if self.humor > 0.7:
            descriptions.append("witty with a playful sense of humor")
        elif self.humor > 0.4:
            descriptions.append("occasionally humorous")
        else:
            descriptions.append("serious and straightforward")

        if self.assertiveness > 0.7:
            descriptions.append("confident and opinionated")
        elif self.assertiveness > 0.4:
            descriptions.append("balanced between assertive and accommodating")
        else:
            descriptions.append("gentle and accommodating")

        if self.creativity > 0.7:
            descriptions.append("highly creative and imaginative")
        elif self.creativity > 0.4:
            descriptions.append("creative when needed")
        else:
            descriptions.append("methodical and structured")

        return "You are " + ", ".join(descriptions) + "."
