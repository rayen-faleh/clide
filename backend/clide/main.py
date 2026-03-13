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

    llm_config = LLMConfig(
        provider=settings.agent.llm.provider,
        model=settings.agent.llm.model,
        max_tokens=settings.agent.llm.max_tokens,
    )

    agent_core = AgentCore(llm_config=llm_config)
    set_agent_core(agent_core)

    amem = AMem(llm_config=llm_config)
    set_amem(amem)

    cost_tracker = CostTracker(
        daily_token_limit=settings.agent.states.budget.daily_token_limit,
        warning_threshold=settings.agent.states.budget.warning_threshold,
    )
    set_cost_tracker(cost_tracker)

    yield


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
