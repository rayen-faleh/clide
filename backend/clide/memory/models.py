"""A-MEM memory data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class MemoryLink:
    """A link between two memories."""

    source_id: str
    target_id: str
    relationship: str  # e.g., "related_to", "contradicts", "elaborates", "caused_by"
    strength: float = 1.0  # 0.0 to 1.0


@dataclass
class Zettel:
    """A single Zettelkasten memory note.

    Each zettel is an atomic unit of knowledge with rich metadata
    and dynamic links to other zettels.
    """

    id: str
    content: str  # Raw content
    summary: str = ""  # LLM-generated one-line summary
    keywords: list[str] = field(default_factory=list)  # Extracted keywords
    tags: list[str] = field(default_factory=list)  # Category tags
    context: str = ""  # Contextual description of when/why this was stored
    importance: float = 0.5  # 0.0 to 1.0, how important this memory is
    links: list[MemoryLink] = field(default_factory=list)  # Links to other zettels
    access_count: int = 0  # How often this memory has been retrieved
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    metadata: dict[str, str] = field(default_factory=dict)  # Arbitrary metadata
