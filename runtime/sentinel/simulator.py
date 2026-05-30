"""
Demo simulator — injects synthetic MarketEvents on schedule or via API/CLI.

Events are published on the ``event`` bus topic (same as Watcher) with ``source: simulator``.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import httpx

from sentinel.bus import TOPIC_EVENT
from sentinel.schemas import MarketEvent

if TYPE_CHECKING:
    from sentinel.bus import EventBus
    from sentinel.config import Settings
    from sentinel.store import SentinelStore

logger = logging.getLogger(__name__)

# (offset_seconds, kind, market, payload)
ScenarioStep = tuple[int, str, str, dict[str, Any]]

SCENARIO_FUNDING_REVERSION: list[ScenarioStep] = [
    (
        0,
        "funding_flip",
        "BTC",
        {
            "old": 0.0008,
            "new": -0.0003,
            "rationale": "Funding flipped negative — shorts now paying longs.",
        },
    ),
    (
        45,
        "drawdown",
        "ETH",
        {
            "position_pct_change": -6.2,
            "rationale": "Open ETH long down 6% in last hour.",
        },
    ),
    (
        120,
        "breakout",
        "INJ",
        {
            "price_change_pct": 3.4,
            "rationale": "INJ broke out of 4h range.",
        },
    ),
]

SCENARIO_RISK_BLOCK: list[ScenarioStep] = [
    (
        0,
        "manual",
        "BTC",
        {
            "force_aggressive": True,
            "rationale": "Demo: trigger an oversized proposal so Risk blocks it.",
        },
    ),
]

SCENARIO_KILL_SWITCH: list[ScenarioStep] = [
    (
        0,
        "drawdown",
        "BTC",
        {
            "position_pct_change": -15,
            "rationale": "Catastrophic drawdown — should trigger halt.",
        },
    ),
]

SCENARIOS: dict[str, list[ScenarioStep]] = {
    "funding_reversion": SCENARIO_FUNDING_REVERSION,
    "risk_block": SCENARIO_RISK_BLOCK,
    "kill_switch": SCENARIO_KILL_SWITCH,
}

_scenario_lock = asyncio.Lock()
_active_scenario_task: asyncio.Task[dict[str, Any]] | None = None


def list_scenarios() -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "steps": len(steps),
            "duration_sec": steps[-1][0] if steps else 0,
        }
        for name, steps in SCENARIOS.items()
    ]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _step_to_event(
    step: ScenarioStep,
    *,
    scenario_name: str | None = None,
) -> MarketEvent:
    _offset, kind, market, payload = step
    full_payload = {
        **payload,
        "scenario": scenario_name,
    }
    return MarketEvent(
        id=str(uuid.uuid4()),
        ts=_utc_now(),
        kind=kind,  # type: ignore[arg-type]
        market=market.upper(),
        payload=full_payload,
        source="simulator",
    )


async def inject_event(
    bus: "EventBus",
    store: "SentinelStore",
    event: MarketEvent,
) -> MarketEvent:
    """Persist and publish a MarketEvent on the ``event`` topic (Watcher-equivalent)."""
    await store.save_event(event)
    await bus.publish(TOPIC_EVENT, event.model_dump(mode="json"))
    logger.info(
        "SIMULATOR inject kind=%s market=%s id=%s scenario=%s",
        event.kind,
        event.market,
        event.id,
        event.payload.get("scenario"),
    )
    return event


async def inject_custom_event(
    bus: "EventBus",
    store: "SentinelStore",
    *,
    kind: str,
    market: str,
    payload: dict[str, Any] | None = None,
    event_id: str | None = None,
) -> MarketEvent:
    event = MarketEvent(
        id=event_id or str(uuid.uuid4()),
        ts=_utc_now(),
        kind=kind,  # type: ignore[arg-type]
        market=market.upper(),
        payload=payload or {},
        source="simulator",
    )
    return await inject_event(bus, store, event)


async def _execute_scenario(
    bus: "EventBus",
    store: "SentinelStore",
    scenario_name: str,
    steps: list[ScenarioStep],
) -> dict[str, Any]:
    started = time.monotonic()
    injected_ids: list[str] = []
    logger.info("SIMULATOR scenario start name=%s steps=%d", scenario_name, len(steps))

    for offset_sec, kind, market, payload in steps:
        elapsed = time.monotonic() - started
        wait = float(offset_sec) - elapsed
        if wait > 0:
            await asyncio.sleep(wait)

        event = _step_to_event(
            (offset_sec, kind, market, payload),
            scenario_name=scenario_name,
        )
        await inject_event(bus, store, event)
        injected_ids.append(event.id)
        logger.info(
            "SIMULATOR scenario step t=%ds kind=%s market=%s id=%s",
            offset_sec,
            kind,
            market,
            event.id,
        )

    duration = time.monotonic() - started
    logger.info(
        "SIMULATOR scenario complete name=%s events=%d duration_sec=%.1f",
        scenario_name,
        len(injected_ids),
        duration,
    )
    return {
        "scenario": scenario_name,
        "status": "completed",
        "event_ids": injected_ids,
        "duration_sec": round(duration, 2),
    }


async def start_scenario(
    bus: "EventBus",
    store: "SentinelStore",
    scenario_name: str,
    *,
    wait: bool = False,
) -> dict[str, Any]:
    """Start a named scenario (background task unless ``wait=True``)."""
    key = scenario_name.strip().lower().replace("-", "_")
    if key not in SCENARIOS:
        raise ValueError(
            f"Unknown scenario '{scenario_name}'. Available: {sorted(SCENARIOS)}"
        )

    global _active_scenario_task

    async def _run() -> dict[str, Any]:
        try:
            return await _execute_scenario(bus, store, key, SCENARIOS[key])
        except asyncio.CancelledError:
            logger.info("SIMULATOR scenario cancelled name=%s", key)
            return {"scenario": key, "status": "cancelled"}
        except Exception as exc:
            logger.exception("SIMULATOR scenario failed name=%s: %s", key, exc)
            return {"scenario": key, "status": "failed", "error": str(exc)}

    async with _scenario_lock:
        if _active_scenario_task and not _active_scenario_task.done():
            _active_scenario_task.cancel()
            try:
                await _active_scenario_task
            except asyncio.CancelledError:
                pass

        if wait:
            return await _run()

        _active_scenario_task = asyncio.create_task(_run(), name=f"sim-{key}")
        return {
            "scenario": key,
            "status": "started",
            "steps": len(SCENARIOS[key]),
            "duration_sec": SCENARIOS[key][-1][0] if SCENARIOS[key] else 0,
        }


async def run_simulator(
    bus: "EventBus",
    store: "SentinelStore",
    config: "Settings",
) -> None:
    """Idle simulator task — scenarios are triggered via API/CLI."""
    if not config.simulator_mode:
        logger.info("Simulator not started (SIMULATOR_MODE=false)")
        return

    await bus.publish("agent.status", {"agent": "simulator", "status": "running"})
    logger.info(
        "Simulator ready — POST /sim/run/{{name}} or `python -m sentinel.simulator run <name>`. "
        "Scenarios: %s",
        sorted(SCENARIOS),
    )
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        global _active_scenario_task
        if _active_scenario_task and not _active_scenario_task.done():
            _active_scenario_task.cancel()
            try:
                await _active_scenario_task
            except asyncio.CancelledError:
                pass
        await bus.publish("agent.status", {"agent": "simulator", "status": "stopped"})
        logger.info("Simulator stopped")
        raise


# Back-compat entry point used by main.py lifespan
async def run(
    *,
    bus: "EventBus",
    store: "SentinelStore",
    config: "Settings",
) -> None:
    await run_simulator(bus, store, config)


# --- CLI ---


async def _cli_run_scenario(
    scenario_name: str,
    *,
    api_url: str,
    wait: bool,
) -> int:
    if api_url:
        url = f"{api_url.rstrip('/')}/sim/run/{scenario_name}"
        params = {"wait": "true"} if wait else {}
        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(url, params=params)
            resp.raise_for_status()
            print(resp.json())
        return 0

    # Direct mode (no HTTP) — for integration tests / embedded use
    from sentinel.bus import EventBus
    from sentinel.config import get_settings
    from sentinel.store import SentinelStore

    settings = get_settings()
    if not settings.simulator_mode:
        print("SIMULATOR_MODE=false — enable in .env", file=sys.stderr)
        return 1

    bus = EventBus()
    store = SentinelStore(settings.sentinel_db_path)
    await store.connect()
    try:
        result = await start_scenario(bus, store, scenario_name, wait=True)
        print(result)
        return 0 if result.get("status") in ("completed", "started") else 1
    finally:
        await store.close()


async def _cli_list() -> int:
    for item in list_scenarios():
        print(
            f"  {item['name']}: {item['steps']} steps, ~{item['duration_sec']}s"
        )
    return 0


def _main() -> None:
    parser = argparse.ArgumentParser(description="iAgent Autopilot demo simulator")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Run a named scenario")
    run_p.add_argument(
        "scenario",
        choices=sorted(SCENARIOS),
        help="Scenario name",
    )
    run_p.add_argument(
        "--api-url",
        default="http://127.0.0.1:8000",
        help="Runtime API base URL (POST /sim/run/...). Use '' for direct inject.",
    )
    run_p.add_argument(
        "--wait",
        action="store_true",
        help="Wait for scenario completion (API: wait=true)",
    )

    sub.add_parser("list", help="List available scenarios")

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    if args.command == "list":
        raise SystemExit(asyncio.run(_cli_list()))

    if args.command == "run":
        api = args.api_url if args.api_url else ""
        raise SystemExit(
            asyncio.run(
                _cli_run_scenario(
                    args.scenario,
                    api_url=api,
                    wait=args.wait,
                )
            )
        )


if __name__ == "__main__":
    _main()
