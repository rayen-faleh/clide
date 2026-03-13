"""Abstract base class for memory storage."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class Memory:
    """A single memory entry."""

    id: str
    content: str
    metadata: dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)


class MemoryStore(ABC):
    """Abstract base class for memory storage backends."""

    @abstractmethod
    async def save(self, content: str, metadata: dict[str, str] | None = None) -> str:
        """Save a memory and return its ID."""
        ...

    @abstractmethod
    async def get(self, memory_id: str) -> Memory | None:
        """Get a memory by ID."""
        ...

    @abstractmethod
    async def search(self, query: str, limit: int = 10) -> list[Memory]:
        """Search memories by keyword."""
        ...

    @abstractmethod
    async def delete(self, memory_id: str) -> bool:
        """Delete a memory by ID."""
        ...

    @abstractmethod
    async def list_all(self, limit: int = 100, offset: int = 0) -> list[Memory]:
        """List all memories with pagination."""
        ...
