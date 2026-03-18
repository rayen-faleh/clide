"""Configuration API routes."""

from __future__ import annotations

import logging
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from clide.api.websocket import get_agent_core
from clide.character.traits import PersonalityTraits
from clide.config.settings import _PROJECT_ROOT, Settings
from clide.core.agent import AgentCore

logger = logging.getLogger(__name__)

# Settings that require a restart to take effect
_RESTART_REQUIRED_KEYS = {"llm", "states"}

config_router = APIRouter(prefix="/api/config", tags=["config"])

CONFIG_PATH = _PROJECT_ROOT / "config" / "agent.yaml"
TOOLS_PATH = _PROJECT_ROOT / "config" / "tools.yaml"
SKILLS_DIR = _PROJECT_ROOT / "skills"


class ConfigUpdate(BaseModel):
    """Partial configuration update."""

    agent: dict[str, Any] | None = None


class SkillUpdate(BaseModel):
    """Skill file content update."""

    content: str


@config_router.get("")
async def get_config() -> dict[str, Any]:
    """Get current configuration."""
    settings = Settings.from_yaml(CONFIG_PATH)
    return settings.model_dump()


@config_router.patch("")
async def update_config(update: ConfigUpdate) -> dict[str, Any]:
    """Update configuration partially.

    Merges the update with existing config and writes back to YAML.
    """
    # Load current
    settings = Settings.from_yaml(CONFIG_PATH)
    current_data = settings.model_dump()

    # Deep merge update
    if update.agent:
        if "agent" not in current_data:
            current_data["agent"] = {}
        _deep_merge(current_data["agent"], update.agent)

    # Validate by parsing back through Settings
    try:
        new_settings = Settings.model_validate(current_data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid configuration: {e}") from e

    # Write back to YAML
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(current_data, f, default_flow_style=False, sort_keys=False)

    # Apply changes to live agent core
    needs_restart = False
    if update.agent:
        needs_restart = bool(_RESTART_REQUIRED_KEYS & update.agent.keys())

    try:
        agent_core = get_agent_core()
        if isinstance(agent_core, AgentCore):
            # Update system prompt
            if new_settings.agent.system_prompt:
                agent_core.system_prompt = new_settings.agent.system_prompt

            # Update character traits
            if agent_core.character is not None:
                new_traits = new_settings.agent.character.base_traits
                agent_core.character.traits = PersonalityTraits(
                    curiosity=new_traits.curiosity,
                    warmth=new_traits.warmth,
                    humor=new_traits.humor,
                    assertiveness=new_traits.assertiveness,
                    creativity=new_traits.creativity,
                )
                await agent_core.character.save()

            if needs_restart:
                logger.info(
                    "Config saved — some changes (llm, states) require restart to take effect"
                )
            else:
                logger.info("Applied config changes to live agent")
    except Exception:
        logger.warning("Failed to apply config to live agent", exc_info=True)

    return new_settings.model_dump()


@config_router.get("/tools/status")
async def get_tools_status() -> dict[str, Any]:
    """Get status of all configured MCP tool servers."""
    tools: list[dict[str, Any]] = []
    if TOOLS_PATH.exists():
        with open(TOOLS_PATH) as f:
            data = yaml.safe_load(f) or {}
        raw_tools = data.get("tools", [])
        if isinstance(raw_tools, list):
            for t in raw_tools:
                if isinstance(t, dict):
                    enabled = t.get("enabled", True)
                    tools.append(
                        {
                            "name": t.get("name", "unknown"),
                            "description": t.get("description", ""),
                            "enabled": enabled,
                            "status": "available" if enabled else "disabled",
                        }
                    )

    return {"tools": tools, "count": len(tools)}


@config_router.get("/tools/{tool_name}/skill")
async def get_tool_skill(tool_name: str) -> dict[str, Any]:
    """Get skill instructions for a tool."""
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    skill_file = SKILLS_DIR / f"{tool_name}.md"
    if skill_file.exists():
        return {"tool_name": tool_name, "content": skill_file.read_text(), "exists": True}
    return {"tool_name": tool_name, "content": "", "exists": False}


@config_router.post("/tools/{tool_name}/skill")
async def save_tool_skill(tool_name: str, body: SkillUpdate) -> dict[str, Any]:
    """Save skill instructions for a tool."""
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    skill_file = SKILLS_DIR / f"{tool_name}.md"
    skill_file.write_text(body.content)
    return {"tool_name": tool_name, "saved": True}


@config_router.delete("/tools/{tool_name}/skill")
async def delete_tool_skill(tool_name: str) -> dict[str, Any]:
    """Delete skill instructions for a tool."""
    skill_file = SKILLS_DIR / f"{tool_name}.md"
    if skill_file.exists():
        skill_file.unlink()
    return {"tool_name": tool_name, "deleted": True}


_scheduler: Any = None


def set_scheduler(scheduler: Any) -> None:
    """Set scheduler reference for pause/resume control."""
    global _scheduler  # noqa: PLW0603
    _scheduler = scheduler


@config_router.get("/thinking/status")
async def get_thinking_status() -> dict[str, Any]:
    """Get thinking scheduler status."""
    if not _scheduler:
        return {"running": False, "paused": False}
    return {
        "running": _scheduler.is_running,
        "paused": _scheduler.is_paused,
        "cycle_count": _scheduler.cycle_count,
        "skipped_count": _scheduler.skipped_count,
    }


@config_router.post("/thinking/pause")
async def pause_thinking() -> dict[str, Any]:
    """Pause the thinking scheduler."""
    if not _scheduler:
        return {"error": "Scheduler not available"}
    _scheduler.pause()
    return {"paused": True}


@config_router.post("/thinking/resume")
async def resume_thinking() -> dict[str, Any]:
    """Resume the thinking scheduler."""
    if not _scheduler:
        return {"error": "Scheduler not available"}
    _scheduler.resume()
    return {"paused": False}


class ToolExecuteRequest(BaseModel):
    """Arguments for tool execution."""

    arguments: dict[str, Any] = {}


@config_router.get("/tools/definitions")
async def list_tool_definitions() -> dict[str, Any]:
    """List all available tools with full schemas, grouped by server."""
    try:
        agent_core = get_agent_core()
        if not isinstance(agent_core, AgentCore) or not agent_core.tool_registry:
            return {"servers": {}, "total": 0}

        registry = agent_core.tool_registry
        all_tools = registry.get_all_tools()

        servers: dict[str, list[dict[str, Any]]] = {}
        for tool in all_tools:
            server = tool.server_name
            if server not in servers:
                servers[server] = []
            servers[server].append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                    "server_name": tool.server_name,
                }
            )

        return {"servers": servers, "total": len(all_tools)}
    except Exception:
        logger.warning("Failed to list tool definitions", exc_info=True)
        return {"servers": {}, "total": 0}


@config_router.post("/tools/{tool_name}/execute")
async def execute_tool(tool_name: str, body: ToolExecuteRequest) -> dict[str, Any]:
    """Execute an MCP tool manually (playground mode)."""
    try:
        agent_core = get_agent_core()
        if not isinstance(agent_core, AgentCore) or not agent_core.tool_registry:
            raise HTTPException(status_code=503, detail="Tool registry not available")

        result = await agent_core.tool_registry.execute_tool(tool_name, body.arguments)

        return {
            "tool_name": tool_name,
            "success": result.success,
            "result": result.result,
            "error": result.error,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Tool execution failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Tool execution failed: {e}") from e


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> None:
    """Deep merge override into base dict (mutates base)."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
