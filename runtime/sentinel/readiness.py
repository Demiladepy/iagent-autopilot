"""Readiness probes for /ready — honest dependency checks."""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sentinel.config import Settings


async def evaluate_readiness(
    *,
    settings: "Settings",
    store: Any,
    agent_tasks: list[asyncio.Task[Any]],
    agent_status: dict[str, str],
    mcp_connected: bool,
    mcp_is_healthy: bool | None,
    lifecycle_ready: bool,
) -> dict[str, Any]:
    """Return readiness report with `ready` bool and `checks` list."""
    checks: list[dict[str, Any]] = []

    if not lifecycle_ready:
        checks.append({"name": "lifecycle", "ok": False, "detail": "still starting or shutting down"})
    else:
        checks.append({"name": "lifecycle", "ok": True})

    store_ok = await _store_reachable(store)
    checks.append(
        {
            "name": "store",
            "ok": store_ok,
            "detail": "sqlite reachable" if store_ok else "database not connected",
        }
    )

    agents_ok, agents_detail = _agents_running(agent_tasks, agent_status)
    checks.append({"name": "agents", "ok": agents_ok, "detail": agents_detail})

    mcp_ok, mcp_detail = _mcp_ready(
        settings=settings,
        mcp_connected=mcp_connected,
        mcp_is_healthy=mcp_is_healthy,
    )
    checks.append({"name": "mcp", "ok": mcp_ok, "detail": mcp_detail})

    ready = all(c["ok"] for c in checks)
    return {
        "ready": ready,
        "checks": checks,
        "simulator_mode": settings.simulator_mode,
        "mcp_connected": mcp_connected,
    }


async def _store_reachable(store: Any) -> bool:
    if getattr(store, "_db", None) is None:
        return False
    try:
        assert store._db is not None
        async with store._db.execute("SELECT 1") as cursor:
            row = await cursor.fetchone()
        return row is not None and row[0] == 1
    except Exception:
        return False


def _agents_running(
    agent_tasks: list[asyncio.Task[Any]],
    agent_status: dict[str, str],
) -> tuple[bool, str]:
    if not agent_tasks:
        return False, "no agent tasks started"
    dead = [t.get_name() or "agent" for t in agent_tasks if t.done()]
    if dead:
        return False, f"agent task(s) exited: {', '.join(dead)}"
    stopped = [name for name, st in agent_status.items() if st == "stopped"]
    if stopped:
        return False, f"agent(s) stopped: {', '.join(stopped)}"
    return True, f"{len(agent_tasks)} agent task(s) running"


def _mcp_ready(
    *,
    settings: "Settings",
    mcp_connected: bool,
    mcp_is_healthy: bool | None,
) -> tuple[bool, str]:
    if settings.simulator_mode:
        return True, "simulator_mode=true (MCP not required)"
    if settings.dry_run:
        return True, "dry_run=true (MCP writes disabled)"
    if not settings.mcp_server_path:
        return False, "MCP_SERVER_PATH not configured"
    if not os.path.isfile(settings.mcp_server_path):
        return False, f"MCP_SERVER_PATH missing on disk: {settings.mcp_server_path}"
    if mcp_is_healthy is False:
        return False, "MCP client unhealthy or crashed"
    if not mcp_connected:
        return False, "MCP client failed to connect on startup"
    return True, "MCP client connected and healthy"
