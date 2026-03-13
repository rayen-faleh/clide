"""HTTP API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
async def health_check(request: Request) -> dict[str, Any]:
    """Health check endpoint."""
    settings = request.app.state.settings
    return {
        "status": "ok",
        "agent_name": settings.agent.name,
    }
