"""iAgent Autopilot FastAPI runtime — dashboard API + agent orchestration."""

from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.websockets import WebSocketDisconnect

from sentinel.agents import AGENT_MODULES
from sentinel.bus import TOPIC_KILL, TOPIC_PROPOSAL, EventBus
from sentinel.config import Settings, get_settings, validate_settings_or_exit
from sentinel.errors import (
    http_exception_handler,
    json_error,
    unhandled_exception_handler,
    validation_exception_handler,
)
from sentinel.llm import anthropic_client
from sentinel.middleware import RequestLoggingMiddleware, SecurityHeadersMiddleware
from sentinel.mcp_client import (
    get_mcp_client,
    mcp_client_is_healthy,
    shutdown_mcp_client,
)
from sentinel.readiness import evaluate_readiness
from sentinel.schemas import MarketEvent, Proposal
from sentinel.security import require_api_key, ws_auth_ok
from sentinel.simulator import (
    inject_event,
    list_scenarios,
    run as simulator_run,
    start_scenario,
)
from sentinel.store import SentinelStore
from sentinel.websocket_hub import WebSocketHub

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

AGENT_NAMES = ["watcher", "analyst", "risk", "executor", "auditor"]
STATE_BROADCAST_INTERVAL_SEC = 10.0
APP_VERSION = "0.1.0"


class AppState:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.bus = EventBus()
        self.store = SentinelStore(settings.sentinel_db_path)
        self.ws_hub = WebSocketHub()
        self.agent_tasks: list[asyncio.Task[Any]] = []
        self.agent_status: dict[str, str] = {n: "idle" for n in AGENT_NAMES}
        self.kill_switch: bool = settings.kill_switch
        self.mcp_connected: bool = False
        self.lifecycle_ready: bool = False
        self.shutting_down: bool = False


def _build_app_state() -> AppState:
    return AppState(get_settings())


def _cors_origins(settings: Settings) -> list[str]:
    origins = settings.cors_origin_list
    if settings.auth_enabled and "*" in origins:
        return [o for o in origins if o != "*"]
    return origins


state = _build_app_state()


class StrategyUpdate(BaseModel):
    text: str | None = None
    max_notional_usd: float | None = Field(default=None, ge=0)
    max_leverage: float | None = Field(default=None, ge=1)
    max_daily_loss_usd: float | None = Field(default=None, ge=0)
    allowed_markets: list[str] | None = None


class StrategyParseRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=8000, description="Natural-language strategy")


class KillSwitchBody(BaseModel):
    enabled: bool


async def _fetch_account_snapshot() -> tuple[Any, Any]:
    if not state.settings.injective_wallet_address:
        return [], {"bank": [], "subaccount": []}
    mcp = await get_mcp_client(state.settings)
    if mcp is None or not mcp.is_healthy():
        return [], {"bank": [], "subaccount": []}
    address = state.settings.injective_wallet_address
    try:
        positions, balances = await asyncio.gather(
            mcp.call("account_positions", {"address": address}),
            mcp.call("account_balances", {"address": address}),
        )
        pos = positions if isinstance(positions, list) else []
        bal = balances if isinstance(balances, dict) else {"bank": [], "subaccount": []}
        return pos, bal
    except Exception as exc:
        logger.warning("Account snapshot failed: %s", exc)
        return [], {"bank": [], "subaccount": []}


async def build_state_snapshot() -> dict[str, Any]:
    positions, balances = await _fetch_account_snapshot()
    return {
        "kill_switch": state.kill_switch,
        "simulator_mode": state.settings.simulator_mode,
        "today_pnl": await state.store.today_pnl(),
        "positions": positions,
        "balances": balances,
        "last_audit": await state.store.get_last_audit(),
        "agents": dict(state.agent_status),
        "mcp_connected": state.mcp_connected,
        "ts": _now_iso(),
    }


async def _state_broadcaster() -> None:
    try:
        while True:
            snapshot = await build_state_snapshot()
            await state.bus.publish("state_update", snapshot)
            await asyncio.sleep(STATE_BROADCAST_INTERVAL_SEC)
    except asyncio.CancelledError:
        raise


async def _status_listener() -> None:
    async for event in state.bus.subscribe("agent.status"):
        agent = event.get("agent")
        status = event.get("status")
        if agent and agent in state.agent_status:
            state.agent_status[agent] = status


async def _readiness_report() -> dict[str, Any]:
    health = mcp_client_is_healthy()
    return await evaluate_readiness(
        settings=state.settings,
        store=state.store,
        agent_tasks=state.agent_tasks,
        agent_status=state.agent_status,
        mcp_connected=state.mcp_connected,
        mcp_is_healthy=health,
        lifecycle_ready=state.lifecycle_ready and not state.shutting_down,
    )


async def _set_kill_switch(enabled: bool) -> dict[str, Any]:
    state.kill_switch = enabled
    state.store.kill_switch_active = enabled
    snapshot = await build_state_snapshot()
    await state.bus.publish(TOPIC_KILL, {"enabled": enabled})
    await state.bus.publish("state_update", snapshot)
    return {"ok": True, "kill_switch": state.kill_switch}


def _require_simulator_mode() -> None:
    if not state.settings.simulator_mode:
        raise HTTPException(
            status_code=400,
            detail="SIMULATOR_MODE is disabled — set SIMULATOR_MODE=true in .env",
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _graceful_shutdown(
    *,
    bg_tasks: list[asyncio.Task[Any]],
) -> None:
    state.shutting_down = True
    state.lifecycle_ready = False

    for task in bg_tasks:
        task.cancel()
    if bg_tasks:
        await asyncio.gather(*bg_tasks, return_exceptions=True)

    for task in state.agent_tasks:
        task.cancel()
    if state.agent_tasks:
        await asyncio.gather(*state.agent_tasks, return_exceptions=True)
    state.agent_tasks.clear()

    await shutdown_mcp_client()
    state.mcp_connected = False
    await state.store.close()
    logger.info("iAgent Autopilot shutdown complete")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Reload from .env / process env (module-level state may have been built at import).
    get_settings.cache_clear()
    state.settings = get_settings()
    app.state.settings = state.settings
    logger.info(
        "DEMO_REAL_TX=%s DRY_RUN=%s",
        state.settings.demo_real_tx,
        state.settings.dry_run,
    )

    validate_settings_or_exit(state.settings)

    await state.store.connect()
    state.store.kill_switch_active = state.kill_switch

    if not state.settings.dry_run and state.settings.mcp_server_path:
        try:
            client = await get_mcp_client(state.settings)
            state.mcp_connected = client is not None and client.is_healthy()
            if state.mcp_connected:
                logger.info("MCP client connected on startup")
            else:
                logger.warning("MCP client unavailable or unhealthy on startup")
        except Exception as exc:
            logger.warning("MCP client failed to start: %s", exc)
            state.mcp_connected = False
    else:
        logger.info(
            "MCP client skipped (dry_run=%s, path=%s)",
            state.settings.dry_run,
            bool(state.settings.mcp_server_path),
        )

    for module in AGENT_MODULES:
        name = module.__name__.split(".")[-1]
        task = asyncio.create_task(
            module.run(bus=state.bus, store=state.store, config=state.settings),
            name=f"agent-{name}",
        )
        state.agent_tasks.append(task)
        state.agent_status[name] = "starting"

    if state.settings.simulator_mode:
        sim_task = asyncio.create_task(
            simulator_run(bus=state.bus, store=state.store, config=state.settings),
            name="simulator",
        )
        state.agent_tasks.append(sim_task)

    bg_tasks = [
        asyncio.create_task(_status_listener(), name="status-listener"),
        asyncio.create_task(_state_broadcaster(), name="state-broadcaster"),
        asyncio.create_task(state.ws_hub.run_fanout(state.bus), name="ws-fanout"),
    ]
    state.lifecycle_ready = True

    logger.info(
        "iAgent Autopilot started env=%s simulator=%s mcp=%s auth=%s",
        state.settings.sentinel_env,
        state.settings.simulator_mode,
        state.mcp_connected,
        state.settings.auth_enabled,
    )

    try:
        yield
    finally:
        logger.info("Shutting down iAgent Autopilot (SIGINT/SIGTERM or process exit)")
        await _graceful_shutdown(bg_tasks=bg_tasks)


def create_app() -> FastAPI:
    settings = state.settings
    app = FastAPI(
        title="iAgent Autopilot",
        description="Autonomous multi-agent trading runtime on Injective MCP",
        version=APP_VERSION,
        lifespan=lifespan,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    app.state.settings = settings

    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(settings),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    public = APIRouter(tags=["public"])
    protected = APIRouter(tags=["protected"], dependencies=[Depends(require_api_key)])

    @public.get("/health")
    async def health() -> dict[str, Any]:
        """Process liveness — always 200 when the server is accepting requests."""
        return {
            "ok": True,
            "version": APP_VERSION,
            "env": state.settings.sentinel_env,
        }

    @public.get("/ready")
    async def ready(request: Request) -> dict[str, Any]:
        """Readiness for traffic — MCP, store, and agents must be healthy."""
        report = await _readiness_report()
        if report["ready"]:
            return {
                "ok": True,
                "version": APP_VERSION,
                "checks": report["checks"],
            }
        failed = [c["name"] for c in report["checks"] if not c["ok"]]
        return json_error(
            status_code=503,
            code="not_ready",
            message=f"Not ready: {', '.join(failed)}",
            request=request,
            details=report["checks"],
        )

    @protected.get("/status")
    async def status() -> dict[str, Any]:
        """Authenticated operational snapshot for the dashboard."""
        return {
            "ok": True,
            "version": APP_VERSION,
            "agents": state.agent_status,
            "kill_switch": state.kill_switch,
            "simulator_mode": state.settings.simulator_mode,
            "mcp_connected": state.mcp_connected,
            "network": state.settings.injective_network,
            "auth_required": state.settings.auth_enabled,
        }

    @protected.get("/strategy")
    async def get_strategy() -> dict[str, Any]:
        return await state.store.get_strategy()

    @protected.put("/strategy")
    async def update_strategy(body: StrategyUpdate) -> dict[str, Any]:
        updated = await state.store.set_strategy(
            text=body.text,
            max_notional_usd=body.max_notional_usd,
            max_leverage=body.max_leverage,
            max_daily_loss_usd=body.max_daily_loss_usd,
            allowed_markets=body.allowed_markets,
        )
        await state.bus.publish("state_update", await build_state_snapshot())
        return updated

    @protected.post("/strategy/parse")
    async def parse_strategy(body: StrategyParseRequest) -> dict[str, Any]:
        proposed = await anthropic_client.parse_strategy_text(state.settings, body.text)
        return {
            "proposed": proposed,
            "current": await state.store.get_strategy(),
            "note": "Review and PUT /strategy to apply.",
        }

    @protected.get("/state")
    async def get_state() -> dict[str, Any]:
        positions, balances = await _fetch_account_snapshot()
        return {
            "positions": positions,
            "balances": balances,
            "today_pnl": await state.store.today_pnl(),
            "kill_switch": state.kill_switch,
            "last_audit": await state.store.get_last_audit(),
            "agents": state.agent_status,
            "simulator_mode": state.settings.simulator_mode,
            "mcp_connected": state.mcp_connected,
            "network": state.settings.injective_network,
        }

    @protected.get("/events")
    async def list_events(limit: int = Query(50, ge=1, le=200)) -> list[dict[str, Any]]:
        return await state.store.recent_market_events(limit=limit)

    @protected.get("/decisions")
    async def list_decisions(limit: int = Query(50, ge=1, le=200)) -> list[dict[str, Any]]:
        return await state.store.recent_decision_chains(limit=limit)

    @protected.get("/journal")
    async def list_journal(limit: int = Query(50, ge=1, le=200)) -> list[dict[str, Any]]:
        return await state.store.recent_journal(n=limit)

    @protected.post("/kill")
    async def kill() -> dict[str, Any]:
        return await _set_kill_switch(True)

    @protected.post("/resume")
    async def resume() -> dict[str, Any]:
        return await _set_kill_switch(False)

    @protected.post("/kill-switch")
    async def kill_switch_legacy(body: KillSwitchBody) -> dict[str, Any]:
        return await _set_kill_switch(body.enabled)

    @protected.get("/sim/scenarios")
    async def sim_list_scenarios() -> list[dict[str, Any]]:
        _require_simulator_mode()
        return list_scenarios()

    @protected.post("/sim/run/{scenario_name}")
    async def sim_run_scenario(
        scenario_name: str,
        wait: bool = Query(False, description="Block until scenario finishes"),
    ) -> dict[str, Any]:
        _require_simulator_mode()
        try:
            return await start_scenario(
                state.bus,
                state.store,
                scenario_name,
                wait=wait,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @protected.post("/sim/event")
    async def sim_inject_event(body: MarketEvent) -> dict[str, Any]:
        _require_simulator_mode()
        event = body.model_copy(
            update={
                "id": body.id or str(uuid.uuid4()),
                "ts": body.ts or datetime.now(timezone.utc),
                "source": "simulator",
            }
        )
        await inject_event(state.bus, state.store, event)
        return {"ok": True, "event": event.model_dump(mode="json")}

    @protected.get("/agents")
    async def list_agents() -> dict[str, Any]:
        return {"agents": state.agent_status}

    @protected.get("/trades")
    async def list_trades(limit: int = Query(50, ge=1, le=200)) -> list[dict[str, Any]]:
        return await state.store.recent_executions(limit=limit)

    @protected.post("/demo/force-open")
    async def demo_force_open() -> dict[str, Any]:
        """
        Deterministic demo trigger.

        Inject a forced BTC open proposal onto the bus so the normal Risk → Executor → Auditor
        pipeline runs without relying on the Analyst's LLM choice.
        """
        if not (state.settings.demo_real_tx or state.settings.simulator_mode):
            raise HTTPException(
                status_code=400,
                detail="Demo trigger disabled (requires DEMO_REAL_TX=true or SIMULATOR_MODE=true)",
            )

        event = MarketEvent(
            id=str(uuid.uuid4()),
            ts=datetime.now(timezone.utc),
            kind="funding_flip",
            market="BTC",
            payload={
                "old": 0.0008,
                "new": -0.0003,
                "rationale": "Demo: deterministic forced open proposal for recording.",
                "scenario": "demo_force_open",
            },
            source="manual",
        )
        await state.store.save_event(event)

        proposal = Proposal(
            id=str(uuid.uuid4()),
            event_id=event.id,
            ts=datetime.now(timezone.utc),
            action="open",
            market="BTC",
            side="short",
            notional_usd=75.0,
            leverage=2.0,
            reasoning="Demo: forced open proposal to deterministically exercise the pipeline.",
            confidence=0.92,
            expected_hold_hours=4.0,
            invalidation="Funding reverts positive and BTC breaks above recent high.",
        )
        await state.store.save_proposal(proposal)
        await state.bus.publish(TOPIC_PROPOSAL, proposal.model_dump(mode="json"))
        await state.bus.publish("state_update", await build_state_snapshot())
        return {"ok": True, "event_id": event.id, "proposal_id": proposal.id}

    app.include_router(public)
    app.include_router(protected)

    @app.websocket("/ws")
    async def websocket_events(websocket: WebSocket) -> None:
        if not ws_auth_ok(state.settings, websocket):
            await websocket.close(code=4401, reason="Unauthorized")
            return

        await websocket.accept()
        await state.ws_hub.register(websocket)
        try:
            await websocket.send_json(
                {"topic": "connected", "ts": _now_iso(), "agents": state.agent_status}
            )
            while True:
                try:
                    await websocket.receive_text()
                except WebSocketDisconnect:
                    break
        finally:
            await state.ws_hub.unregister(websocket)

    return app


app = create_app()
