"""Character manager — ties personality, mood, and opinions together."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import aiosqlite

from clide.character.mood import MoodState
from clide.character.opinions import OpinionStore
from clide.character.traits import PersonalityTraits

logger = logging.getLogger(__name__)

CREATE_CHARACTER_SQL = """
CREATE TABLE IF NOT EXISTS character_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
)
"""


class Character:
    """The agent's character — personality, mood, and opinions.

    Persists state to SQLite so the character survives restarts.
    """

    def __init__(
        self,
        traits: PersonalityTraits | None = None,
        mood: MoodState | None = None,
        db_path: str | Path = "data/character.db",
    ) -> None:
        self.traits = traits or PersonalityTraits()
        self.mood = mood or MoodState()
        self.opinions = OpinionStore()
        self.db_path = str(db_path)
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        """Ensure the database table exists."""
        if not self._initialized:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(CREATE_CHARACTER_SQL)
                await db.commit()
            self._initialized = True

    def build_personality_prompt(self) -> str:
        """Build personality additions for the system prompt.

        Combines trait description and mood description.
        """
        parts = [self.traits.describe(), self.mood.describe()]

        # Add relevant opinions if any
        opinions = self.opinions.all()
        if opinions:
            opinion_strs = [
                f"- On {op.topic}: {op.stance}"
                for op in sorted(opinions, key=lambda o: o.confidence, reverse=True)[:5]
            ]
            parts.append("Your current opinions:\n" + "\n".join(opinion_strs))

        return "\n".join(parts)

    async def save(self) -> None:
        """Persist character state to SQLite."""
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as db:
            # Save traits
            await db.execute(
                "INSERT OR REPLACE INTO character_state (key, value) VALUES (?, ?)",
                ("traits", json.dumps(self.traits.to_dict())),
            )
            # Save mood
            await db.execute(
                "INSERT OR REPLACE INTO character_state (key, value) VALUES (?, ?)",
                ("mood", json.dumps(self.mood.to_dict())),
            )
            # Save opinions
            await db.execute(
                "INSERT OR REPLACE INTO character_state (key, value) VALUES (?, ?)",
                ("opinions", json.dumps(self.opinions.to_list())),
            )
            await db.commit()
        logger.info("Character state saved to DB")

    async def load(self) -> None:
        """Load character state from SQLite."""
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            # Load traits
            cursor = await db.execute(
                "SELECT value FROM character_state WHERE key = ?", ("traits",)
            )
            row = await cursor.fetchone()
            if row:
                self.traits = PersonalityTraits.from_dict(json.loads(row["value"]))

            # Load mood
            cursor = await db.execute("SELECT value FROM character_state WHERE key = ?", ("mood",))
            row = await cursor.fetchone()
            if row:
                self.mood = MoodState.from_dict(json.loads(row["value"]))

            # Load opinions
            cursor = await db.execute(
                "SELECT value FROM character_state WHERE key = ?", ("opinions",)
            )
            row = await cursor.fetchone()
            if row:
                self.opinions = OpinionStore.from_list(json.loads(row["value"]))
        logger.info("Character state loaded from DB")
