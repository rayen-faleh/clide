# NOTE: This router must be registered in main.py:
#   from clide.api.memory_routes import memory_router, cost_router
#   app.include_router(memory_router)
#   app.include_router(cost_router)
"""Memory API routes for browsing and searching the memory graph."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from clide.core.cost import CostTracker
from clide.memory.amem import AMem
from clide.memory.models import Zettel

logger = logging.getLogger(__name__)

memory_router = APIRouter(prefix="/api/memories", tags=["memories"])

# Global AMem instance — will be set during app startup
_amem: AMem | None = None


def set_amem(amem: AMem) -> None:
    """Set the global AMem instance."""
    global _amem  # noqa: PLW0603
    _amem = amem


def get_amem() -> AMem:
    """Get the global AMem instance."""
    if _amem is None:
        msg = "AMem not initialized"
        raise RuntimeError(msg)
    return _amem


def _zettel_to_dict(z: Zettel) -> dict[str, Any]:
    """Convert a Zettel to a JSON-serializable dict."""
    return {
        "id": z.id,
        "content": z.content,
        "summary": z.summary,
        "keywords": z.keywords,
        "tags": z.tags,
        "context": z.context,
        "importance": z.importance,
        "access_count": z.access_count,
        "links": [
            {
                "target_id": link.target_id,
                "relationship": link.relationship,
                "strength": link.strength,
            }
            for link in z.links
        ],
        "created_at": z.created_at.isoformat(),
        "updated_at": z.updated_at.isoformat(),
        "metadata": z.metadata,
    }


@memory_router.get("")
async def list_memories(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """List memories with pagination."""
    amem = get_amem()
    zettels = await amem.list_recent(limit=limit, offset=offset)
    return {
        "memories": [_zettel_to_dict(z) for z in zettels],
        "count": len(zettels),
        "offset": offset,
        "limit": limit,
    }


@memory_router.get("/search")
async def search_memories(
    q: str = Query(description="Search query"),
    limit: int = Query(default=10, ge=1, le=50),
) -> dict[str, Any]:
    """Search memories semantically."""
    amem = get_amem()
    results = await amem.recall(q, limit=limit, use_spreading=True)
    return {
        "query": q,
        "results": [_zettel_to_dict(z) for z in results],
        "count": len(results),
    }


@memory_router.get("/graph")
async def get_memory_graph(
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    """Get memory graph data (nodes and edges) for visualization."""
    amem = get_amem()
    zettels = await amem.list_recent(limit=limit)

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, str]] = set()

    for z in zettels:
        nodes.append(
            {
                "id": z.id,
                "label": z.summary or z.content[:50],
                "importance": z.importance,
                "access_count": z.access_count,
                "tags": z.tags,
                "created_at": z.created_at.isoformat(),
            }
        )

        # Get links for this zettel
        full_z = await amem.get(z.id)
        if full_z:
            for link in full_z.links:
                edge_key = (link.source_id, link.target_id)
                if edge_key not in seen_edges:
                    edges.append(
                        {
                            "source": link.source_id,
                            "target": link.target_id,
                            "relationship": link.relationship,
                            "strength": link.strength,
                        }
                    )
                    seen_edges.add(edge_key)

    return {
        "nodes": nodes,
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges),
    }


@memory_router.get("/{memory_id}")
async def get_memory(memory_id: str) -> dict[str, Any]:
    """Get a single memory by ID."""
    amem = get_amem()
    zettel = await amem.get(memory_id)
    if zettel is None:
        return {"error": "Memory not found", "id": memory_id}
    return _zettel_to_dict(zettel)


class MemoryUploadItem(BaseModel):
    """A single memory to upload."""

    content: str
    summary: str = ""
    keywords: list[str] = []
    tags: list[str] = []
    importance: float = 0.5
    timestamp: str = ""
    metadata: dict[str, str] = {}


class MemoryUploadRequest(BaseModel):
    """Request body for uploading memories."""

    memories: list[MemoryUploadItem]


@memory_router.post("/upload")
async def upload_memories(body: MemoryUploadRequest) -> dict[str, Any]:
    """Upload fabricated memories directly into A-MEM (bypasses LLM extraction)."""
    amem = get_amem()
    created_ids: list[str] = []

    for item in body.memories:
        zettel_id = str(uuid.uuid4())

        # Use provided timestamp or default to now
        if item.timestamp:
            try:
                ts = datetime.fromisoformat(item.timestamp)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=UTC)
            except ValueError:
                ts = datetime.now(UTC)
        else:
            ts = datetime.now(UTC)

        zettel = Zettel(
            id=zettel_id,
            content=item.content,
            summary=item.summary,
            keywords=item.keywords,
            tags=item.tags,
            importance=max(0.0, min(1.0, item.importance)),
            created_at=ts,
            updated_at=ts,
            metadata={**item.metadata, "type": "uploaded_memory"},
        )

        # Store in SQLite (bypasses LLM extraction pipeline)
        await amem._save_zettel(zettel)

        # Store in ChromaDB for semantic search
        await amem.chroma.add(
            zettel_id,
            item.content,
            metadata={"type": "uploaded_memory"},
        )

        created_ids.append(zettel_id)

    logger.info("Uploaded %d memories", len(created_ids))
    return {"created": len(created_ids), "ids": created_ids}


# --- Cost stats router ---

cost_router = APIRouter(prefix="/api/stats", tags=["stats"])

_cost_tracker: CostTracker | None = None


def set_cost_tracker(tracker: CostTracker) -> None:
    """Set the global CostTracker instance."""
    global _cost_tracker  # noqa: PLW0603
    _cost_tracker = tracker


def get_cost_tracker() -> CostTracker:
    """Get the global CostTracker instance."""
    if _cost_tracker is None:
        msg = "CostTracker not initialized"
        raise RuntimeError(msg)
    return _cost_tracker


@cost_router.get("/costs")
async def get_cost_stats() -> dict[str, object]:
    """Get token usage and budget stats."""
    tracker = get_cost_tracker()
    return tracker.get_stats()
