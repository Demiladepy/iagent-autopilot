"""Watcher agent — polls Injective via MCP and emits MarketEvents (no trading)."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sentinel.agents.resilience import log_agent_loop_error
from sentinel.bus import TOPIC_EVENT, TOPIC_KILL, TOPIC_SIM_INJECT
from sentinel.llm import groq_client
from sentinel.mcp_client import MCPError, get_mcp_client
from sentinel.schemas import MarketEvent

if TYPE_CHECKING:
    from sentinel.bus import EventBus
    from sentinel.config import Settings
    from sentinel.store import SentinelStore

logger = logging.getLogger(__name__)
AGENT_NAME = "watcher"

RING_SIZE = 60
BREAKOUT_WINDOW_SEC = 60
BREAKOUT_PCT = 0.02
DRAWDOWN_PCT = -5.0
DRIFT_PCT = 0.10


@dataclass
class PriceSample:
    ts: datetime
    price: float
    funding_rate: float | None


@dataclass
class MarketRing:
    samples: deque[PriceSample] = field(default_factory=lambda: deque(maxlen=RING_SIZE))
    last_funding_sign: int = 0  # -1, 0, +1


def _parse_markets(config: "Settings", strategy: dict[str, Any]) -> list[str]:
    if config.watcher_markets.strip():
        return [m.strip().upper() for m in config.watcher_markets.split(",") if m.strip()]
    allowed = strategy.get("allowed_markets") or ["BTC", "ETH", "INJ"]
    return [m.upper() for m in allowed]


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _funding_sign(rate: float | None) -> int:
    if rate is None or rate == 0:
        return 0
    return 1 if rate > 0 else -1


def _position_key(symbol: str, side: str) -> str:
    return f"{symbol.upper()}:{side.lower()}"


def _extract_price(data: Any) -> float | None:
    if isinstance(data, dict):
        for key in ("price", "markPrice", "oraclePrice"):
            if key in data:
                return _safe_float(data[key], default=-1) if data[key] is not None else None
        return None
    if isinstance(data, (int, float, str)):
        return _safe_float(data, default=-1)
    return None


def _extract_funding(data: Any) -> float | None:
    if not isinstance(data, dict):
        return None
    for key in (
        "fundingRate",
        "funding_rate",
        "hourlyFundingRate",
        "hourly_funding_rate",
        "funding",
    ):
        if key in data and data[key] is not None:
            return _safe_float(data[key])
    return None


def _unrealized_pnl_pct(position: dict[str, Any]) -> float:
    margin = _safe_float(position.get("margin"))
    pnl = _safe_float(position.get("unrealizedPnl"))
    if margin <= 0:
        return 0.0
    return (pnl / margin) * 100.0


class Watcher:
    def __init__(
        self,
        *,
        bus: "EventBus",
        store: "SentinelStore",
        config: "Settings",
        kill_event: asyncio.Event,
    ) -> None:
        self.bus = bus
        self.store = store
        self.config = config
        self.kill_event = kill_event
        self.markets: list[str] = []
        self.rings: dict[str, MarketRing] = {}
        self._last_pnl_pct: dict[str, float] = {}
        self._mcp = None

    async def run(self) -> None:
        strategy = await self.store.get_strategy()
        self.markets = _parse_markets(self.config, strategy)
        for m in self.markets:
            self.rings.setdefault(m, MarketRing())

        if not self.config.simulator_mode and self.config.mcp_server_path:
            self._mcp = await get_mcp_client(self.config)

        await self.bus.publish("agent.status", {"agent": "watcher", "status": "running"})
        logger.info(
            "Watcher started: markets=%s poll_interval=%ss simulator=%s",
            self.markets,
            self.config.poll_interval,
            self.config.simulator_mode,
        )

        poll_task = asyncio.create_task(self._poll_loop(), name="watcher-poll")
        sim_task = None
        if self.config.simulator_mode:
            sim_task = asyncio.create_task(self._sim_inject_loop(), name="watcher-sim-inject")

        await self.kill_event.wait()

        poll_task.cancel()
        if sim_task:
            sim_task.cancel()
        for task in (poll_task, sim_task):
            if task:
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        await self.bus.publish("agent.status", {"agent": "watcher", "status": "stopped"})
        logger.info("Watcher stopped (kill received)")

    async def _sim_inject_loop(self) -> None:
        try:
            async for msg in self.bus.subscribe(TOPIC_SIM_INJECT):
                if self.kill_event.is_set():
                    return
                try:
                    event = MarketEvent.model_validate(
                        {k: v for k, v in msg.items() if k != "topic"}
                    )
                    await self._emit(event, from_sim_inject=True)
                except Exception as exc:
                    log_agent_loop_error(AGENT_NAME, exc, context="sim_inject")
        except asyncio.CancelledError:
            raise

    async def _poll_loop(self) -> None:
        try:
            while not self.kill_event.is_set():
                try:
                    await self._poll_once()
                except Exception as exc:
                    log_agent_loop_error(AGENT_NAME, exc, context="poll")
                try:
                    await asyncio.wait_for(
                        self.kill_event.wait(),
                        timeout=self.config.poll_interval,
                    )
                    break
                except asyncio.TimeoutError:
                    pass
        except asyncio.CancelledError:
            raise

    async def _poll_once(self) -> None:
        if self._mcp is None or not self._mcp.is_healthy():
            if not self.config.simulator_mode:
                logger.debug("Watcher poll skipped — MCP not connected or unhealthy")
            return

        now = datetime.now(timezone.utc)
        price_tasks = [
            self._mcp.call("market_price", {"symbol": market})
            for market in self.markets
        ]
        pos_task = None
        if self.config.injective_wallet_address:
            pos_task = self._mcp.call(
                "account_positions",
                {"address": self.config.injective_wallet_address},
            )

        results = await asyncio.gather(*price_tasks, return_exceptions=True)
        positions: list[dict[str, Any]] = []
        if pos_task is not None:
            pos_result = await asyncio.gather(pos_task, return_exceptions=True)
            if pos_result and not isinstance(pos_result[0], BaseException):
                raw = pos_result[0]
                positions = raw if isinstance(raw, list) else []

        market_prices: dict[str, float] = {}
        market_funding: dict[str, float | None] = {}

        for market, result in zip(self.markets, results):
            if isinstance(result, BaseException):
                logger.warning("market_price %s failed: %s", market, result)
                continue
            price = _extract_price(result)
            if price is None or price < 0:
                logger.warning("market_price %s returned no price: %s", market, result)
                continue
            market_prices[market] = price
            market_funding[market] = _extract_funding(result)

        baselines = await self.store.position_baselines_from_journal()

        for market, price in market_prices.items():
            ring = self.rings.setdefault(market, MarketRing())
            funding = market_funding.get(market)
            if funding is None and len(ring.samples) >= 2:
                prev = ring.samples[-1].price
                if prev > 0:
                    funding = ((price - prev) / prev) * 100.0

            sample = PriceSample(ts=now, price=price, funding_rate=funding)
            ring.samples.append(sample)

            await self._detect_breakout(market, ring, price, now)
            await self._detect_funding_flip(market, ring, funding)

        for pos in positions:
            await self._detect_drawdown(pos, now)
            await self._detect_position_drift(pos, baselines, now)

    async def _detect_breakout(
        self, market: str, ring: MarketRing, price: float, now: datetime
    ) -> None:
        if len(ring.samples) < 2:
            return
        window = [
            s for s in ring.samples if (now - s.ts).total_seconds() <= BREAKOUT_WINDOW_SEC
        ]
        if len(window) < 2:
            return
        mean_price = sum(s.price for s in window) / len(window)
        if mean_price <= 0:
            return
        move_pct = abs(price - mean_price) / mean_price
        if move_pct <= BREAKOUT_PCT:
            return
        direction = "up" if price > mean_price else "down"
        event = MarketEvent(
            id=str(uuid.uuid4()),
            ts=now,
            kind="breakout",
            market=market,
            payload={
                "price": price,
                "mean_price": round(mean_price, 6),
                "move_pct": round(move_pct * 100, 4),
                "direction": direction,
                "window_sec": BREAKOUT_WINDOW_SEC,
            },
            source="watcher",
        )
        await self._emit(event)

    async def _detect_funding_flip(
        self, market: str, ring: MarketRing, funding: float | None
    ) -> None:
        if funding is None:
            return
        sign = _funding_sign(funding)
        if sign == 0:
            return
        if ring.last_funding_sign != 0 and sign != ring.last_funding_sign:
            event = MarketEvent(
                id=str(uuid.uuid4()),
                ts=datetime.now(timezone.utc),
                kind="funding_flip",
                market=market,
                payload={
                    "funding_rate": funding,
                    "previous_sign": ring.last_funding_sign,
                    "new_sign": sign,
                },
                source="watcher",
            )
            await self._emit(event)
        ring.last_funding_sign = sign

    async def _detect_drawdown(self, position: dict[str, Any], now: datetime) -> None:
        symbol = str(position.get("symbol", "")).upper()
        side = str(position.get("side", "")).lower()
        if not symbol:
            return
        key = _position_key(symbol, side)
        pnl_pct = _unrealized_pnl_pct(position)
        prev = self._last_pnl_pct.get(key)
        self._last_pnl_pct[key] = pnl_pct

        crossed = pnl_pct < DRAWDOWN_PCT and (prev is None or prev >= DRAWDOWN_PCT)
        if not crossed:
            return

        event = MarketEvent(
            id=str(uuid.uuid4()),
            ts=now,
            kind="drawdown",
            market=symbol,
            payload={
                "side": side,
                "unrealized_pnl_pct": round(pnl_pct, 4),
                "unrealized_pnl": position.get("unrealizedPnl"),
                "margin": position.get("margin"),
                "quantity": position.get("quantity"),
                "mark_price": position.get("markPrice"),
            },
            source="watcher",
        )
        await self._emit(event)

    async def _detect_position_drift(
        self,
        position: dict[str, Any],
        baselines: dict[str, float],
        now: datetime,
    ) -> None:
        symbol = str(position.get("symbol", "")).upper()
        side = str(position.get("side", "")).lower()
        key = _position_key(symbol, side)
        baseline = baselines.get(key)
        if baseline is None or baseline <= 0:
            return
        current = _safe_float(position.get("quantity"))
        if current <= 0:
            current = _safe_float(position.get("margin"))
        drift = abs(current - baseline) / baseline
        if drift <= DRIFT_PCT:
            return
        event = MarketEvent(
            id=str(uuid.uuid4()),
            ts=now,
            kind="position_drift",
            market=symbol,
            payload={
                "side": side,
                "baseline": baseline,
                "current": current,
                "drift_pct": round(drift * 100, 4),
                "quantity": position.get("quantity"),
            },
            source="watcher",
        )
        await self._emit(event)

    async def _emit(self, event: MarketEvent, *, from_sim_inject: bool = False) -> None:
        description = _template_description(event)
        try:
            description = await groq_client.describe_event(
                self.config, event.model_dump(mode="json")
            )
        except Exception as exc:
            logger.debug("Groq description fallback: %s", exc)

        payload = {**event.payload, "description": description}
        if from_sim_inject:
            payload["sim_injected"] = True
        event = event.model_copy(update={"payload": payload})

        await self.store.save_event(event)
        await self.bus.publish(TOPIC_EVENT, event.model_dump(mode="json"))
        logger.info(
            "Watcher event kind=%s market=%s payload_keys=%s description=%s",
            event.kind,
            event.market,
            list(event.payload.keys()),
            description[:120],
        )


def _template_description(event: MarketEvent) -> str:
    p = event.payload
    if event.kind == "breakout":
        return (
            f"{event.market} broke {p.get('direction', '?')} "
            f"{p.get('move_pct', '?')}% vs {p.get('window_sec', 60)}s mean."
        )
    if event.kind == "drawdown":
        return (
            f"{event.market} {p.get('side', '')} position drawdown "
            f"{p.get('unrealized_pnl_pct', '?')}% unrealized PnL."
        )
    if event.kind == "position_drift":
        return (
            f"{event.market} {p.get('side', '')} size drifted "
            f"{p.get('drift_pct', '?')}% from journal baseline."
        )
    if event.kind == "funding_flip":
        return f"{event.market} funding rate sign flipped (rate={p.get('funding_rate')})."
    if event.kind == "synthetic":
        return f"Synthetic {event.market} tick (price={p.get('price')})."
    return f"{event.market} {event.kind} detected."


async def _kill_listener(bus: "EventBus", kill_event: asyncio.Event) -> None:
    async for msg in bus.subscribe(TOPIC_KILL):
        if msg.get("enabled", True):
            kill_event.set()
            logger.warning("Watcher received kill signal")
            return


async def run(
    *,
    bus: "EventBus",
    store: "SentinelStore",
    config: "Settings",
) -> None:
    kill_event = asyncio.Event()
    kill_task = asyncio.create_task(_kill_listener(bus, kill_event), name="watcher-kill")

    watcher = Watcher(bus=bus, store=store, config=config, kill_event=kill_event)
    try:
        await watcher.run()
    except asyncio.CancelledError:
        await bus.publish("agent.status", {"agent": "watcher", "status": "stopped"})
        raise
    finally:
        kill_task.cancel()
        try:
            await kill_task
        except asyncio.CancelledError:
            pass
