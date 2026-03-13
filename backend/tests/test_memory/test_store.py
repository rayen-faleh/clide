"""Tests for the memory store ABC."""

from __future__ import annotations

import pytest

from clide.memory.store import MemoryStore


class TestMemoryStoreABC:
    def test_memory_store_is_abstract(self) -> None:
        with pytest.raises(TypeError):
            MemoryStore()  # type: ignore[abstract]
