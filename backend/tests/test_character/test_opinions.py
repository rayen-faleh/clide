"""Tests for opinion system module."""

from __future__ import annotations

from clide.character.opinions import Opinion, OpinionStore


class TestOpinion:
    def test_opinion_creation(self) -> None:
        opinion = Opinion(topic="Python", stance="Great language for rapid prototyping")
        assert opinion.topic == "Python"
        assert opinion.stance == "Great language for rapid prototyping"
        assert opinion.confidence == 0.5
        assert opinion.interaction_count == 1

    def test_opinion_update_blends(self) -> None:
        opinion = Opinion(topic="Python", stance="Good language", confidence=0.5)
        opinion.update("Excellent language", 0.9, "Used it more")
        # confidence should have changed via blending
        assert opinion.confidence != 0.5
        assert opinion.interaction_count == 2

    def test_opinion_interaction_count_increments(self) -> None:
        opinion = Opinion(topic="Testing", stance="Important", confidence=0.6)
        opinion.update("Very important", 0.8)
        opinion.update("Essential", 0.9)
        assert opinion.interaction_count == 3


class TestOpinionStore:
    def test_opinion_store_get_set(self) -> None:
        store = OpinionStore()
        opinion = Opinion(topic="Python", stance="Great language")
        store.set(opinion)
        retrieved = store.get("Python")
        assert retrieved is not None
        assert retrieved.topic == "Python"

    def test_opinion_store_update_existing(self) -> None:
        store = OpinionStore()
        store.set(Opinion(topic="Python", stance="Good", confidence=0.5))
        store.set(Opinion(topic="Python", stance="Great", confidence=0.8))
        retrieved = store.get("python")  # Case insensitive
        assert retrieved is not None
        assert retrieved.interaction_count == 2

    def test_opinion_store_relevant(self) -> None:
        store = OpinionStore()
        store.set(Opinion(topic="Python programming", stance="Great"))
        store.set(Opinion(topic="Rust language", stance="Fast"))
        store.set(Opinion(topic="Cooking", stance="Fun"))
        results = store.relevant(["Python"])
        assert len(results) == 1
        assert results[0].topic == "Python programming"

    def test_opinion_store_relevant_no_match(self) -> None:
        store = OpinionStore()
        store.set(Opinion(topic="Python", stance="Great"))
        results = store.relevant(["JavaScript"])
        assert len(results) == 0

    def test_opinion_store_serialization_round_trip(self) -> None:
        store = OpinionStore()
        store.set(Opinion(topic="Python", stance="Great", confidence=0.8))
        store.set(Opinion(topic="Testing", stance="Important", confidence=0.6))
        data = store.to_list()
        restored = OpinionStore.from_list(data)
        assert len(restored.all()) == 2
        assert restored.get("python") is not None
        assert restored.get("testing") is not None
