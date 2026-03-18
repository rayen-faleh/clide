"""REST endpoints for workshop mode."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

workshop_router = APIRouter(prefix="/api/workshop", tags=["workshop"])
_agent_core: Any = None


def set_agent_core(core: Any) -> None:
    """Set the agent core reference for workshop routes."""
    global _agent_core  # noqa: PLW0603
    _agent_core = core


@workshop_router.get("/session")
async def get_session() -> dict[str, Any]:
    """Get the current workshop session state."""
    if not _agent_core:
        return {"session": None}
    session = _agent_core.get_workshop_session()
    if not session:
        return {"session": None}
    return {
        "session": {
            "id": session.id,
            "goal_description": session.goal_description,
            "status": session.status,
            "current_step_index": session.current_step_index,
            "plan": (
                {
                    "objective": session.plan.objective,
                    "approach": session.plan.approach,
                    "steps": [
                        {
                            "id": s.id,
                            "description": s.description,
                            "tools_needed": s.tools_needed,
                            "success_criteria": s.success_criteria,
                            "status": s.status,
                            "result_summary": s.result_summary,
                        }
                        for s in session.plan.steps
                    ],
                }
                if session.plan
                else None
            ),
            "inner_dialogue": session.inner_dialogue[-50:],
            "created_at": session.created_at.isoformat(),
        },
    }


@workshop_router.post("/discard")
async def discard_session() -> dict[str, Any]:
    """Discard the current workshop session."""
    if not _agent_core:
        return {"error": "Agent not initialized"}
    await _agent_core.discard_workshop()
    return {"status": "discarded"}


class ResumeRequest(BaseModel):
    """Request body for resuming a workshop."""

    goal_description: str
    goal_id: str = "resumed-workshop"


@workshop_router.post("/resume")
async def resume_session(body: ResumeRequest) -> dict[str, Any]:
    """Resume a workshop session with a goal description."""
    if not _agent_core:
        return {"error": "Agent not initialized"}

    # Set up workshop broadcast
    from clide.api.schemas import (
        WorkshopStartedPayload,
        WSMessage,
        WSMessageType,
    )
    from clide.api.websocket import manager as ws_manager

    # Build a broadcast function for workshop events
    from clide.main import _build_workshop_broadcast

    broadcast_fn = _build_workshop_broadcast()
    _agent_core.set_tool_event_callback(broadcast_fn)

    await ws_manager.broadcast(
        WSMessage(
            type=WSMessageType.WORKSHOP_STARTED,
            payload=WorkshopStartedPayload(
                session_id="pending",
                goal_description=body.goal_description,
            ).model_dump(),
        )
    )

    success = await _agent_core.enter_workshop(body.goal_id, body.goal_description)
    if success:
        return {"status": "resumed", "goal_description": body.goal_description}
    return {"error": "Cannot enter workshop mode right now"}
