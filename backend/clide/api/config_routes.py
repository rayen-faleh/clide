"""Configuration API routes."""

from __future__ import annotations

from typing import Any

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from clide.config.settings import _PROJECT_ROOT, Settings

config_router = APIRouter(prefix="/api/config", tags=["config"])

CONFIG_PATH = _PROJECT_ROOT / "config" / "agent.yaml"
TOOLS_PATH = _PROJECT_ROOT / "config" / "tools.yaml"


class ConfigUpdate(BaseModel):
    """Partial configuration update."""

    agent: dict[str, Any] | None = None


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


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> None:
    """Deep merge override into base dict (mutates base)."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
