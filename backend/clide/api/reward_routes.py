"""REST API endpoints for the virtual pizza reward system."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

from clide.api.schemas import RewardEventPayload, RewardGivePayload, WSMessage, WSMessageType

logger = logging.getLogger(__name__)

reward_router = APIRouter(prefix="/api/rewards", tags=["rewards"])

# Set during app startup from main.py
_agent_core: Any = None


def set_agent_core(core: Any) -> None:
    """Wire the agent core instance for reward operations."""
    global _agent_core  # noqa: PLW0603
    _agent_core = core


@reward_router.post("/give")
async def give_reward(body: RewardGivePayload) -> dict[str, Any]:
    """Give virtual pizzas to the agent."""
    if _agent_core is None:
        return {"error": "Agent not initialized"}

    total = await _agent_core.give_reward(body.amount, body.reason)

    # Broadcast via WebSocket
    from clide.api.websocket import manager as ws_manager

    await ws_manager.broadcast(
        WSMessage(
            type=WSMessageType.REWARD_GIVEN,
            payload=RewardEventPayload(
                amount=body.amount,
                reason=body.reason,
                total_earned=total,
            ).model_dump(),
        )
    )

    return {"total_earned": total}


@reward_router.get("/summary")
async def get_reward_summary() -> dict[str, Any]:
    """Get total pizzas and recent reward history."""
    if _agent_core is None:
        return {"total": 0, "recent": []}

    total = await _agent_core._get_total_pizzas()

    recent: list[dict[str, Any]] = []
    if _agent_core.amem:
        rewards = await _agent_core.amem.get_recent_by_type("reward", limit=10)
        for r in rewards:
            recent.append(
                {
                    "amount": r.metadata.get("amount", "0"),
                    "reason": r.metadata.get("reason", ""),
                    "created_at": r.created_at.isoformat() if r.created_at else "",
                }
            )

    return {"total": total, "recent": recent}
