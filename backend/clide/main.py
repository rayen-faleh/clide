"""CLIDE FastAPI application."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from clide.api.config_routes import config_router
from clide.api.conversation_routes import conversation_router, set_conversation_store
from clide.api.goal_routes import goal_router, set_goal_manager
from clide.api.memory_routes import cost_router, memory_router, set_amem, set_cost_tracker
from clide.api.routes import router
from clide.api.websocket import set_agent_core, ws_router
from clide.autonomy.goals import GoalManager
from clide.autonomy.scheduler import ThinkingScheduler
from clide.character.character import Character
from clide.character.traits import PersonalityTraits
from clide.config.settings import Settings
from clide.core.agent import AgentCore
from clide.core.conversation_store import ConversationStore
from clide.core.cost import CostTracker
from clide.core.llm import LLMConfig
from clide.core.prompts import DEFAULT_SYSTEM_PROMPT
from clide.memory.amem import AMem
from clide.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


def _load_or_create_born_at() -> datetime:
    """Load or create the agent's birth timestamp."""
    born_file = Path("data/born_at.txt")
    born_file.parent.mkdir(parents=True, exist_ok=True)
    if born_file.exists():
        return datetime.fromisoformat(born_file.read_text().strip())
    now = datetime.now(UTC)
    born_file.write_text(now.isoformat())
    return now


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan: startup and shutdown."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # Set clide loggers to DEBUG for verbose output
    logging.getLogger("clide").setLevel(logging.DEBUG)

    settings = Settings.from_yaml()
    app.state.settings = settings

    # LLM config
    llm_config = LLMConfig(
        provider=settings.agent.llm.provider,
        model=settings.agent.llm.model,
        max_tokens=settings.agent.llm.max_tokens,
        api_base=settings.agent.llm.api_base,
    )
    logger.info(
        "Initializing LLM config: provider=%s, model=%s",
        settings.agent.llm.provider,
        settings.agent.llm.model,
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
    trait_dict = character.traits.to_dict()
    logger.info("Character loaded (traits: %s)", trait_dict)

    # Conversation store
    conversation_store = ConversationStore()
    set_conversation_store(conversation_store)

    # Agent core — pass all deps
    born_at = _load_or_create_born_at()
    agent_core = AgentCore(
        llm_config=llm_config,
        system_prompt=settings.agent.system_prompt or DEFAULT_SYSTEM_PROMPT,
        amem=amem,
        character=character,
        cost_tracker=cost_tracker,
        conversation_store=conversation_store,
        born_at=born_at,
    )
    set_agent_core(agent_core)

    # Tool registry
    tool_registry = ToolRegistry.from_yaml()
    connection_results = await tool_registry.connect_all()
    logger.info(
        "Tool registry initialized: %d servers, %d tools available",
        tool_registry.server_count,
        tool_registry.tool_count,
    )
    for server_name, connected in connection_results.items():
        logger.info(
            "  MCP server '%s': %s",
            server_name,
            "connected" if connected else "FAILED",
        )

    agent_core.tool_registry = tool_registry

    # Goal manager
    goal_manager = GoalManager()
    agent_core.goal_manager = goal_manager
    set_goal_manager(goal_manager)

    # Autonomy scheduler
    scheduler = ThinkingScheduler(
        interval_seconds=settings.agent.states.thinking.interval_seconds,
    )

    # Define the thinking callback
    async def thinking_callback() -> None:
        logger.debug("Thinking callback triggered")
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
            logger.info("Thought broadcast to %d clients", len(ws_manager.active_connections))
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
        interval = settings.agent.states.thinking.interval_seconds
        logger.info("Autonomy scheduler started (interval: %ss)", interval)

    yield

    # Shutdown
    logger.info("Saving character state...")
    await tool_registry.disconnect_all()
    logger.info("Tool registry disconnected")
    await scheduler.stop()
    logger.info("Scheduler stopped")
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
    app.include_router(conversation_router)
    app.include_router(goal_router)

    return app


app = create_app()
