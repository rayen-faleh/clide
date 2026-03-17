"""REST endpoints for workshop mode."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

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
