"""Memory processing pipeline for A-MEM."""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any

from clide.core.llm import LLMConfig, stream_completion
from clide.memory.models import MemoryLink, Zettel

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """Analyze the following content and extract structured information.
Return a JSON object with these fields:
- "summary": A one-line summary (max 100 chars)
- "keywords": A list of 3-7 keywords
- "tags": A list of 1-3 category tags (e.g., "personal", "factual", "opinion", "experience")
- "context": A brief description of the context (1-2 sentences)
- "importance": A float 0.0-1.0 indicating how important this seems

Content: {content}

Return ONLY valid JSON, no other text."""

LINK_PROMPT = """Given a new memory and a list of existing memories, \
identify which existing memories are related.
For each related memory, specify the relationship type.

New memory:
{new_content}

Existing memories:
{existing_memories}

Return a JSON array of objects with:
- "target_id": The ID of the related existing memory
- "relationship": One of "related_to", "contradicts", "elaborates", "caused_by", "similar_to"
- "strength": A float 0.0-1.0 indicating relationship strength

Return ONLY valid JSON array. If no relations found, return []."""


def _extract_json(text: str) -> Any:
    """Extract JSON from LLM response that may contain markdown or preamble.

    Tries in order:
    1. Parse the whole string as JSON
    2. Extract from ```json ... ``` code blocks
    3. Find the first [ or { and parse from there
    """
    text = text.strip()

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from code block
    match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Try finding first JSON structure
    for start_char, end_char in [("[", "]"), ("{", "}")]:
        start = text.find(start_char)
        if start != -1:
            end = text.rfind(end_char)
            if end > start:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    pass

    raise json.JSONDecodeError("No valid JSON found", text, 0)


class MemoryProcessor:
    """Processes raw content into rich Zettel memories."""

    def __init__(self, llm_config: LLMConfig | None = None) -> None:
        self.llm_config = llm_config or LLMConfig()

    async def process(
        self,
        content: str,
        existing_zettels: list[Zettel] | None = None,
        metadata: dict[str, str] | None = None,
    ) -> Zettel:
        """Process raw content into a Zettel.

        1. Extract keywords, summary, tags, context, importance via LLM
        2. Find links to existing memories
        3. Create and return the Zettel
        """
        # Step 1: Extract structured info
        extraction = await self._extract_info(content)

        # Step 2: Find links to existing memories
        links: list[MemoryLink] = []
        memory_id = str(uuid.uuid4())
        if existing_zettels:
            links = await self._find_links(content, memory_id, existing_zettels)

        # Step 3: Create Zettel
        zettel = Zettel(
            id=memory_id,
            content=content,
            summary=extraction.get("summary", ""),
            keywords=extraction.get("keywords", []),
            tags=extraction.get("tags", []),
            context=extraction.get("context", ""),
            importance=float(extraction.get("importance", 0.5)),
            links=links,
            metadata=metadata or {},
        )

        return zettel

    async def _extract_info(self, content: str) -> dict[str, Any]:
        """Extract keywords, summary, tags from content via LLM."""
        prompt = EXTRACTION_PROMPT.format(content=content)
        messages = [{"role": "user", "content": prompt}]

        response_text = ""
        async for chunk in stream_completion(messages, self.llm_config):
            response_text += chunk

        try:
            result: dict[str, Any] = _extract_json(response_text)
            return result
        except json.JSONDecodeError:
            logger.warning("Failed to parse extraction response: %s", response_text[:200])
            return {
                "summary": content[:100],
                "keywords": [],
                "tags": [],
                "context": "",
                "importance": 0.5,
            }

    async def _find_links(
        self,
        content: str,
        memory_id: str,
        existing: list[Zettel],
    ) -> list[MemoryLink]:
        """Find links between new content and existing memories."""
        existing_str = "\n".join(
            f"- ID: {z.id} | Summary: {z.summary} | Keywords: {', '.join(z.keywords)}"
            for z in existing[:20]  # Limit to 20 to manage context
        )

        prompt = LINK_PROMPT.format(
            new_content=content,
            existing_memories=existing_str,
        )
        messages = [{"role": "user", "content": prompt}]

        response_text = ""
        async for chunk in stream_completion(messages, self.llm_config):
            response_text += chunk

        try:
            links_data: list[dict[str, object]] = _extract_json(response_text)
            if not isinstance(links_data, list):
                return []
            return [
                MemoryLink(
                    source_id=memory_id,
                    target_id=str(link["target_id"]),
                    relationship=str(link.get("relationship", "related_to")),
                    strength=float(link.get("strength", 0.5)),  # type: ignore[arg-type]
                )
                for link in links_data
                if isinstance(link, dict) and "target_id" in link
            ]
        except (json.JSONDecodeError, KeyError):
            logger.warning("Failed to parse links response: %s", response_text[:200])
            return []
