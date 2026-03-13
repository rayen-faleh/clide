"""Agent opinion system — forms and maintains opinions on topics."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class Opinion:
    """An opinion the agent holds on a topic."""

    topic: str
    stance: str  # The agent's view on the topic
    confidence: float = 0.5  # 0.0-1.0, how strongly held
    reasoning: str = ""  # Why the agent holds this opinion
    formed_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    interaction_count: int = 1  # How many times this topic came up

    def update(self, new_stance: str, new_confidence: float, new_reasoning: str = "") -> None:
        """Update the opinion, blending with existing view."""
        # Opinions become stronger with repeated exposure
        self.interaction_count += 1

        # Blend confidence
        weight = min(0.4, 1.0 / self.interaction_count)
        self.confidence = self.confidence * (1 - weight) + new_confidence * weight
        self.confidence = max(0.0, min(1.0, self.confidence))

        # Update stance if new confidence is high enough
        if new_confidence > self.confidence:
            self.stance = new_stance

        if new_reasoning:
            self.reasoning = new_reasoning

        self.updated_at = datetime.now(UTC)

    def to_dict(self) -> dict[str, str | float | int]:
        """Serialize opinion."""
        return {
            "topic": self.topic,
            "stance": self.stance,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "formed_at": self.formed_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "interaction_count": self.interaction_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, str | float | int]) -> Opinion:
        """Deserialize opinion."""
        return cls(
            topic=str(data["topic"]),
            stance=str(data["stance"]),
            confidence=float(data.get("confidence", 0.5)),
            reasoning=str(data.get("reasoning", "")),
            formed_at=(
                datetime.fromisoformat(str(data["formed_at"]))
                if "formed_at" in data
                else datetime.now(UTC)
            ),
            updated_at=(
                datetime.fromisoformat(str(data["updated_at"]))
                if "updated_at" in data
                else datetime.now(UTC)
            ),
            interaction_count=int(data.get("interaction_count", 1)),
        )


class OpinionStore:
    """In-memory store for agent opinions."""

    def __init__(self) -> None:
        self._opinions: dict[str, Opinion] = {}

    def get(self, topic: str) -> Opinion | None:
        """Get opinion on a topic."""
        return self._opinions.get(topic.lower())

    def set(self, opinion: Opinion) -> None:
        """Store or update an opinion."""
        key = opinion.topic.lower()
        existing = self._opinions.get(key)
        if existing:
            existing.update(opinion.stance, opinion.confidence, opinion.reasoning)
        else:
            self._opinions[key] = opinion

    def all(self) -> list[Opinion]:
        """Get all opinions."""
        return list(self._opinions.values())

    def relevant(self, keywords: list[str], limit: int = 5) -> list[Opinion]:
        """Find opinions relevant to given keywords."""
        results: list[tuple[int, Opinion]] = []
        for opinion in self._opinions.values():
            score = sum(
                1
                for kw in keywords
                if kw.lower() in opinion.topic.lower() or kw.lower() in opinion.stance.lower()
            )
            if score > 0:
                results.append((score, opinion))

        results.sort(key=lambda x: x[0], reverse=True)
        return [op for _, op in results[:limit]]

    def to_list(self) -> list[dict[str, str | float | int]]:
        """Serialize all opinions."""
        return [op.to_dict() for op in self._opinions.values()]

    @classmethod
    def from_list(cls, data: list[dict[str, str | float | int]]) -> OpinionStore:
        """Deserialize opinions."""
        store = cls()
        for item in data:
            store._opinions[str(item["topic"]).lower()] = Opinion.from_dict(item)
        return store
