"""Smallville MCP Server — wraps Smallville HTTP API as MCP tools.

Run standalone: python -m clide.tools.smallville_mcp
Configure in config/tools.yaml to run as an MCP server.

Environment variables:
    SMALLVILLE_URL: Smallville server URL (default: http://localhost:8080)
    CLIDE_AGENT_NAME: Agent name in the village (default: Clide)
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

SMALLVILLE_URL = os.environ.get("SMALLVILLE_URL", "http://localhost:8080")
AGENT_NAME = os.environ.get("CLIDE_AGENT_NAME", "Clide")

TOOLS = [
    {
        "name": "observe_village",
        "description": (
            "See the full state of the village - all agents,"
            " their activities, locations, and ongoing conversations."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "look_around",
        "description": "Get a list of all locations in the village and their current state.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "observe_agent",
        "description": (
            "See what a specific villager is doing right now"
            " - their location, activity, and current state."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The villager's name"}
            },
            "required": ["name"],
        },
    },
    {
        "name": "talk_to_villager",
        "description": (
            "Have a conversation with a villager."
            " Ask them a question and hear their response."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The villager's name"},
                "question": {"type": "string", "description": "What to say or ask"},
            },
            "required": ["name", "question"],
        },
    },
    {
        "name": "introduce_yourself",
        "description": (
            "Register yourself as a new character in the village"
            " at a specific location."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "Where to appear in the village",
                },
                "activity": {
                    "type": "string",
                    "description": "What you're doing when you arrive",
                },
            },
            "required": ["location", "activity"],
        },
    },
    {
        "name": "share_memory",
        "description": (
            "Tell a villager something - this becomes part of"
            " their memory and may influence their behavior."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "The villager to tell",
                },
                "memory": {
                    "type": "string",
                    "description": "What to share with them",
                },
            },
            "required": ["agent_name", "memory"],
        },
    },
    {
        "name": "advance_time",
        "description": (
            "Move the village simulation forward one time step."
            " All agents will act and react."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_village_info",
        "description": "Get current village time, simulation stats, and recent activity.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def _http_request(
    method: str, path: str, body: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Make HTTP request to Smallville server."""
    url = f"{SMALLVILLE_URL}{path}"
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"} if body else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())  # type: ignore[no-any-return]
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.reason}"}
    except urllib.error.URLError as e:
        return {"error": f"Connection failed: {e.reason}"}
    except Exception as e:
        return {"error": str(e)}


def _execute_tool(name: str, arguments: dict[str, Any]) -> str:  # noqa: C901
    """Execute a tool and return the result as a human-readable string."""
    if name == "observe_village":
        result = _http_request("GET", "/state")
        if "error" in result:
            return f"Could not observe village: {result['error']}"
        agents = result.get("agents", [])
        convos = result.get("conversations", [])
        lines = ["=== Village State ==="]
        for a in agents:
            lines.append(
                f"- {a.get('name', '?')}: {a.get('activity', '?')} "
                f"at {a.get('location', '?')}"
            )
        if convos:
            lines.append("\nOngoing conversations:")
            for c in convos:
                lines.append(f"  {c}")
        return "\n".join(lines)

    elif name == "look_around":
        result = _http_request("GET", "/locations")
        if "error" in result:
            return f"Could not look around: {result['error']}"
        locations = result.get("locations", [])
        lines = ["=== Locations ==="]
        for loc in locations:
            lines.append(f"- {loc.get('name', '?')}: {loc.get('state', '')}")
        return "\n".join(lines)

    elif name == "observe_agent":
        agent_name = arguments.get("name", "")
        result = _http_request("GET", f"/agents/{agent_name}")
        if "error" in result:
            return f"Could not find {agent_name}: {result['error']}"
        return json.dumps(result, indent=2)

    elif name == "talk_to_villager":
        agent_name = arguments.get("name", "")
        question = arguments.get("question", "")
        result = _http_request(
            "POST", f"/agents/{agent_name}/ask", {"question": question}
        )
        answer = result.get("answer", result.get("error", "No response"))
        return f"{agent_name} says: {answer}"

    elif name == "introduce_yourself":
        location = arguments.get("location", "Town Square")
        activity = arguments.get("activity", "looking around curiously")
        result = _http_request(
            "POST",
            "/agents",
            {
                "name": AGENT_NAME,
                "memories": [
                    f"I am {AGENT_NAME}, a curious and thoughtful being.",
                    "I just arrived in this village and want to meet the locals.",
                ],
                "location": location,
                "activity": activity,
            },
        )
        if result.get("success"):
            return f"You ({AGENT_NAME}) entered the village at {location}, {activity}."
        return f"Failed to enter village: {result}"

    elif name == "share_memory":
        agent_name = arguments.get("agent_name", "")
        memory = arguments.get("memory", "")
        result = _http_request(
            "POST", "/memories", {"name": agent_name, "memory": memory}
        )
        if result.get("success"):
            return f"Shared with {agent_name}: '{memory}'"
        return f"Failed to share memory: {result}"

    elif name == "advance_time":
        result = _http_request("POST", "/state")
        if "error" in result:
            return f"Could not advance time: {result['error']}"
        agents = result.get("agents", [])
        lines = ["=== Time Advanced ==="]
        for a in agents:
            lines.append(f"- {a.get('name', '?')}: {a.get('activity', '?')}")
        return "\n".join(lines)

    elif name == "get_village_info":
        result = _http_request("GET", "/info")
        if "error" in result:
            return f"Could not get info: {result['error']}"
        return json.dumps(result, indent=2)

    return f"Unknown tool: {name}"


def _handle_message(message: dict[str, Any]) -> dict[str, Any] | None:
    """Handle a JSON-RPC message. Returns response dict or None for notifications."""
    method = message.get("method", "")
    msg_id = message.get("id")
    params = message.get("params", {})

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "smallville-mcp", "version": "1.0.0"},
            },
        }

    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"tools": TOOLS},
        }

    elif method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        try:
            result_text = _execute_tool(tool_name, arguments)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": result_text}],
                    "isError": False,
                },
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": f"Error: {e}"}],
                    "isError": True,
                },
            }

    elif method.startswith("notifications/"):
        return None

    else:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }


def main() -> None:
    """Main loop: read JSON-RPC from stdin, process, write to stdout."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
            response = _handle_message(message)
            if response is not None:
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
        except json.JSONDecodeError:
            pass
        except Exception as e:
            error_resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32603, "message": str(e)},
            }
            sys.stdout.write(json.dumps(error_resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
