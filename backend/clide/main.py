"""CLIDE FastAPI application."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from clide.api.config_routes import config_router
from clide.api.memory_routes import cost_router, memory_router, set_amem, set_cost_tracker
from clide.api.routes import router
from clide.api.websocket import set_agent_core, ws_router
from clide.autonomy.goals import GoalManager
from clide.autonomy.scheduler import ThinkingScheduler
from clide.character.character import Character
from clide.character.traits import PersonalityTraits
from clide.config.settings import Settings
from clide.core.agent import AgentCore
from clide.core.cost import CostTracker
from clide.core.llm import LLMConfig
from clide.memory.amem import AMem


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan: startup and shutdown."""
    settings = Settings.from_yaml()
    app.state.settings = settings

    # LLM config
    llm_config = LLMConfig(
        provider=settings.agent.llm.provider,
        model=settings.agent.llm.model,
        max_tokens=settings.agent.llm.max_tokens,
        api_base=settings.agent.llm.api_base,
    )

    # Cost tracker
    cost_tracker = CostTracker(
        daily_token_limit=settings.agent.states.budget.daily_token_limit,
        warning_threshold=settings.agent.states.budget.warning_threshold,
    )
    set_cost_tracker(cost_tracker)

    # Memory
    amem = AMem(llm_config=llm_config)
    set_amem(amem)

    # Character
    character = Character(
        traits=PersonalityTraits.from_dict(settings.agent.character.base_traits.model_dump()),
    )
    await character.load()  # Load persisted state if exists

    # Agent core — pass all deps
    agent_core = AgentCore(
        llm_config=llm_config,
        amem=amem,
        character=character,
        cost_tracker=cost_tracker,
    )
    set_agent_core(agent_core)

    # Goal manager (instantiated for future use)
    GoalManager()

    # Autonomy scheduler
    scheduler = ThinkingScheduler(
        interval_seconds=settings.agent.states.thinking.interval_seconds,
    )

    # Define the thinking callback
    async def thinking_callback() -> None:
        result = await agent_core.autonomous_think()
        if result:
            thought_content, mood, intensity = result
            # Late import to avoid circular imports
            from clide.api.schemas import (
                MoodPayload,
                ThoughtPayload,
                WSMessage,
                WSMessageType,
            )
            from clide.api.websocket import manager as ws_manager

            # Broadcast thought to all connected clients
            await ws_manager.broadcast(
                WSMessage(
                    type=WSMessageType.THOUGHT,
                    payload=ThoughtPayload(
                        content=thought_content,
                        source="autonomous",
                    ).model_dump(),
                )
            )
            # Broadcast mood update
            await ws_manager.broadcast(
                WSMessage(
                    type=WSMessageType.MOOD_UPDATE,
                    payload=MoodPayload(
                        mood=mood,
                        intensity=intensity,
                        reason="autonomous thinking",
                    ).model_dump(),
                )
            )

    if settings.agent.states.thinking.interval_seconds > 0:
        scheduler.set_callback(thinking_callback)
        await scheduler.start()

    yield

    # Shutdown
    await scheduler.stop()
    await character.save()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="CLIDE",
        description="Curiosity-driven AI agent",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # TODO: restrict in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router, prefix="/api")
    app.include_router(ws_router)
    app.include_router(memory_router)
    app.include_router(cost_router)
    app.include_router(config_router)

    return app


app = create_app()
