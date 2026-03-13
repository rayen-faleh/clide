"""Tests for A-MEM data models."""

from __future__ import annotations

from datetime import UTC, datetime

from clide.memory.models import MemoryLink, Zettel


class TestZettel:
    def test_zettel_creation_defaults(self) -> None:
        zettel = Zettel(id="z1", content="Hello world")
        assert zettel.id == "z1"
        assert zettel.content == "Hello world"
        assert zettel.summary == ""
        assert zettel.keywords == []
        assert zettel.tags == []
        assert zettel.context == ""
        assert zettel.importance == 0.5
        assert zettel.links == []
        assert zettel.access_count == 0
        assert isinstance(zettel.created_at, datetime)
        assert isinstance(zettel.updated_at, datetime)
        assert zettel.metadata == {}

    def test_zettel_with_all_fields(self) -> None:
        now = datetime.now(UTC)
        link = MemoryLink(source_id="z1", target_id="z2", relationship="related_to")
        zettel = Zettel(
            id="z1",
            content="Test content",
            summary="A test",
            keywords=["test", "example"],
            tags=["factual"],
            context="Unit test context",
            importance=0.9,
            links=[link],
            access_count=5,
            created_at=now,
            updated_at=now,
            metadata={"source": "test"},
        )
        assert zettel.summary == "A test"
        assert zettel.keywords == ["test", "example"]
        assert zettel.tags == ["factual"]
        assert zettel.context == "Unit test context"
        assert zettel.importance == 0.9
        assert len(zettel.links) == 1
        assert zettel.access_count == 5
        assert zettel.created_at == now
        assert zettel.metadata == {"source": "test"}


class TestMemoryLink:
    def test_memory_link_defaults(self) -> None:
        link = MemoryLink(source_id="a", target_id="b", relationship="related_to")
        assert link.source_id == "a"
        assert link.target_id == "b"
        assert link.relationship == "related_to"
        assert link.strength == 1.0

    def test_memory_link_custom(self) -> None:
        link = MemoryLink(
            source_id="x",
            target_id="y",
            relationship="contradicts",
            strength=0.7,
        )
        assert link.relationship == "contradicts"
        assert link.strength == 0.7
