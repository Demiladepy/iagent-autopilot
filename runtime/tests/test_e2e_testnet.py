"""
Live testnet integration — real Injective MCP, real wallet, DRY_RUN execution.

Skipped in the default test run (see pytest.ini). Run before a demo recording:

    cd runtime
    pytest -m integration -s

Two tests:
  test_e2e_pipeline_forced — gate: proposal injected on bus → risk → executor → audit (deterministic).
  test_e2e_analyst_live    — real Analyst on funding_flip; asserts proposal persisted (any action).

Requires runtime/.env with ANTHROPIC_API_KEY, GROQ_API_KEY, MCP_SERVER_PATH,
INJECTIVE_WALLET_ADDRESS, INJECTIVE_WALLET_PASSWORD, and a funded testnet wallet.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import tempfile
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest

from sentinel.agents import analyst, auditor, executor, risk
from sentinel.agents.watcher import _extract_price
from sentinel.bus import TOPIC_PROPOSAL, EventBus
from sentinel.config import collect_config_issues, get_settings
from sentinel.mcp_client import (
    InjectiveMCPClient,
    shutdown_mcp_client,
)
from sentinel.schemas import MarketEvent, Proposal
from sentinel.simulator import inject_event
from sentinel.store import SentinelStore

pytestmark = pytest.mark.integration

logger = logging.getLogger(__name__)

RUNTIME_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = RUNTIME_DIR / ".env"
EXPECTED_MCP_TOOL_COUNT = 28
FORCED_PIPELINE_TIMEOUT_SEC = 120.0
ANALYST_PIPELINE_TIMEOUT_SEC = 240.0
POLL_INTERVAL_SEC = 2.0

DOWNSTREAM_AGENTS = [risk, executor, auditor]
LIVE_AGENTS = [analyst, risk, executor, auditor]

FUNDING_FLIP_PAYLOAD = {
    "old": 0.0008,
    "new": -0.0003,
    "rationale": "E2E: funding flipped negative — shorts now paying longs.",
    "scenario": "e2e_testnet",
}

FORCED_STRATEGY_TEXT = (
    "E2E forced pipeline: small BTC trades within limits are allowed for integration tests."
)

ANALYST_STRATEGY_TEXT = (
    "On funding_flip events where funding turns negative, you may propose a small BTC "
    "short hedge (notional <= $150, leverage <= 2x) or return none if unclear. "
    "Both outcomes are valid."
)


def _require_integration_prereqs() -> None:
    if not shutil.which("node"):
        pytest.skip("node not on PATH — required for Injective MCP server")
    if not ENV_FILE.is_file():
        pytest.skip(f"runtime/.env not found at {ENV_FILE}")


def _load_integration_settings():
    """Reload settings from runtime/.env with testnet + dry-run overrides."""
    from sentinel.config import get_settings as _gs

    _gs.cache_clear()
    os.environ.setdefault("SENTINEL_ENV", "development")
    os.environ["SIMULATOR_MODE"] = "false"
    os.environ["DRY_RUN"] = "true"
    os.environ["INJECTIVE_NETWORK"] = "testnet"
    os.environ.setdefault("MCP_HANDSHAKE_TIMEOUT", "60")
    os.environ.setdefault("MCP_TOOL_CALL_TIMEOUT", "60")
    os.environ.setdefault("MCP_REQUEST_TIMEOUT", "120")
    os.environ["SENTINEL_DB_PATH"] = tempfile.mktemp(
        prefix="e2e-testnet-",
        suffix=".db",
        dir=str(RUNTIME_DIR),
    )
    settings = _gs()
    issues = collect_config_issues(settings)
    if issues:
        pytest.skip("Configuration incomplete for integration run:\n" + "\n".join(f"  - {i}" for i in issues))
    if not settings.mcp_server_path or not Path(settings.mcp_server_path).is_file():
        pytest.skip(f"MCP_SERVER_PATH not found: {settings.mcp_server_path!r}")
    if not settings.injective_wallet_address.strip():
        pytest.skip("INJECTIVE_WALLET_ADDRESS not set in runtime/.env")
    return settings


async def _install_mcp_singleton(settings) -> InjectiveMCPClient:
    """Start real MCP and expose it to agents (get_mcp_client skips when DRY_RUN=true)."""
    import sentinel.mcp_client as mcp_module

    await shutdown_mcp_client()
    client = InjectiveMCPClient.from_settings(settings)
    await client.start()
    mcp_module._mcp_singleton = client
    return client


def _assert_markets_non_empty(markets: Any) -> list[Any]:
    if isinstance(markets, list):
        assert len(markets) > 0, "market_list returned an empty list"
        return markets
    if isinstance(markets, dict):
        for key in ("markets", "data", "result"):
            inner = markets.get(key)
            if isinstance(inner, list) and inner:
                return inner
    raise AssertionError(f"Unexpected market_list shape: {type(markets).__name__}")


def _assert_price_present(raw: Any) -> float:
    price = _extract_price(raw)
    if price is None or price < 0:
        raise AssertionError(f"market_price returned no usable price: {raw!r}")
    return price


def _print_json(label: str, data: Any) -> None:
    print(f"\n=== {label} ===")
    print(json.dumps(data, indent=2, default=str))


async def _inject_proposal(
    bus: EventBus,
    store: SentinelStore,
    proposal: Proposal,
) -> Proposal:
    """Publish a proposal like the Analyst — Risk+ downstream agents consume TOPIC_PROPOSAL."""
    await store.save_proposal(proposal)
    await bus.publish(TOPIC_PROPOSAL, proposal.model_dump(mode="json"))
    logger.info(
        "E2E injected proposal id=%s action=%s market=%s",
        proposal.id,
        proposal.action,
        proposal.market,
    )
    return proposal


def _chain_for_proposal(chains: list[dict[str, Any]], proposal_id: str) -> dict[str, Any] | None:
    for chain in chains:
        proposal = chain.get("proposal") or {}
        if str(proposal.get("id")) == proposal_id:
            return chain
    return None


async def _wait_for_forced_chain(
    store: SentinelStore,
    proposal_id: str,
    *,
    timeout_sec: float,
) -> dict[str, Any]:
    """Wait for verdict → dry-run execution → audit after a forced proposal."""
    deadline = time.monotonic() + timeout_sec
    last_partial: dict[str, Any] | None = None

    while time.monotonic() < deadline:
        chains = await store.recent_decision_chains(limit=20)
        chain = _chain_for_proposal(chains, proposal_id)
        if chain is None:
            await asyncio.sleep(POLL_INTERVAL_SEC)
            continue

        last_partial = chain
        proposal = chain.get("proposal")
        verdict = chain.get("verdict")
        execution = chain.get("execution")
        audit = chain.get("audit")

        if not (proposal and verdict and execution and audit):
            await asyncio.sleep(POLL_INTERVAL_SEC)
            continue

        if not verdict.get("approved"):
            raise AssertionError(
                f"Risk rejected forced proposal: reasons={verdict.get('reasons')!r}"
            )

        if execution.get("status") != "success":
            raise AssertionError(
                f"Execution status={execution.get('status')!r}, expected 'success'; "
                f"error={execution.get('error')!r}"
            )

        tx_hash = str(execution.get("tx_hash") or "")
        if not tx_hash.startswith("dry-run-"):
            raise AssertionError(f"Expected dry-run tx_hash, got {tx_hash!r}")

        assert proposal.get("action") == "open"
        return chain

    detail = json.dumps(last_partial, indent=2, default=str) if last_partial else "(no chain)"
    raise AssertionError(
        f"Timed out after {timeout_sec}s waiting for forced pipeline (proposal_id={proposal_id}).\n"
        f"Last partial state:\n{detail}"
    )


async def _wait_for_proposal(
    store: SentinelStore,
    event_id: str,
    *,
    timeout_sec: float,
) -> dict[str, Any]:
    """Wait until the Analyst persists a proposal for the given event."""
    deadline = time.monotonic() + timeout_sec

    while time.monotonic() < deadline:
        chains = await store.recent_decision_chains(limit=20)
        for chain in chains:
            event = chain.get("event") or {}
            if str(event.get("id")) != event_id:
                continue
            proposal = chain.get("proposal")
            if proposal:
                return chain
        await asyncio.sleep(POLL_INTERVAL_SEC)

    raise AssertionError(
        f"Timed out after {timeout_sec}s waiting for Analyst proposal (event_id={event_id})"
    )


async def _start_agents(
    bus: EventBus,
    store: SentinelStore,
    settings: Any,
    modules: list[Any],
) -> list[asyncio.Task[Any]]:
    tasks: list[asyncio.Task[Any]] = []
    for module in modules:
        name = module.__name__.split(".")[-1]
        tasks.append(
            asyncio.create_task(
                module.run(bus=bus, store=store, config=settings),
                name=f"e2e-agent-{name}",
            )
        )
    await asyncio.sleep(0.5)
    return tasks


async def _stop_agents(tasks: list[asyncio.Task[Any]]) -> None:
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


@asynccontextmanager
async def _e2e_runtime() -> AsyncIterator[tuple[Any, EventBus, SentinelStore, list[asyncio.Task[Any]]]]:
    """Shared store + empty agent list; callers start MCP and agents."""
    _require_integration_prereqs()
    settings = _load_integration_settings()
    bus = EventBus()
    store = SentinelStore(settings.sentinel_db_path)
    await store.connect()
    tasks: list[asyncio.Task[Any]] = []
    try:
        yield settings, bus, store, tasks
    finally:
        await _stop_agents(tasks)
        await shutdown_mcp_client()
        await store.close()
        db = Path(settings.sentinel_db_path)
        if db.is_file():
            try:
                db.unlink()
            except OSError:
                pass


async def _mcp_smoke(mcp: InjectiveMCPClient, wallet_address: str) -> None:
    assert mcp.is_healthy()
    tool_count = len(mcp.tools)
    assert tool_count == EXPECTED_MCP_TOOL_COUNT, (
        f"Expected {EXPECTED_MCP_TOOL_COUNT} MCP tools, got {tool_count}"
    )
    print(f"\nMCP tools listed: {tool_count}")

    markets_raw = await mcp.call("market_list", {})
    markets = _assert_markets_non_empty(markets_raw)
    print(f"market_list: {len(markets)} market(s)")

    price_raw = await mcp.call("market_price", {"symbol": "BTC"})
    btc_price = _assert_price_present(price_raw)
    print(f"market_price BTC: {btc_price}")

    balances_raw = await mcp.call("account_balances", {"address": wallet_address})
    _print_json(f"account_balances ({wallet_address})", balances_raw)
    assert balances_raw is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_e2e_pipeline_forced() -> None:
    """
    Gate test: forced open proposal on the bus → Risk → Executor (dry-run) → Auditor.

    Bypasses the Analyst. Groq risk sanity is stubbed to APPROVE so this validates
    orchestration and MCP wiring, not LLM judgment (see test_e2e_analyst_live).
    """
    async with _e2e_runtime() as (settings, bus, store, tasks):
        await store.set_strategy(
            text=FORCED_STRATEGY_TEXT,
            max_notional_usd=500.0,
            max_leverage=3.0,
            max_daily_loss_usd=500.0,
            allowed_markets=["BTC", "ETH", "INJ"],
        )

        await _install_mcp_singleton(settings)
        tasks.extend(await _start_agents(bus, store, settings, DOWNSTREAM_AGENTS))

        event_id = str(uuid.uuid4())
        event = MarketEvent(
            id=event_id,
            ts=datetime.now(timezone.utc),
            kind="funding_flip",
            market="BTC",
            payload={**FUNDING_FLIP_PAYLOAD, "e2e": "pipeline_forced"},
            source="simulator",
        )
        await store.save_event(event)

        proposal = Proposal(
            id=str(uuid.uuid4()),
            event_id=event_id,
            ts=datetime.now(timezone.utc),
            action="open",
            market="BTC",
            side="short",
            notional_usd=75.0,
            leverage=2.0,
            reasoning="E2E forced pipeline: deterministic open proposal for integration gate.",
            confidence=0.92,
            expected_hold_hours=4.0,
            invalidation="BTC funding reverts positive and price breaks above recent high.",
        )

        groq_approve = AsyncMock(return_value=(True, "e2e_forced: groq stubbed APPROVE", 1.0))
        with patch("sentinel.agents.risk.groq_client.risk_sanity_check", groq_approve):
            await _inject_proposal(bus, store, proposal)
            print(f"\nForced proposal id={proposal.id} action=open market=BTC")

            chain = await _wait_for_forced_chain(
                store,
                proposal.id,
                timeout_sec=FORCED_PIPELINE_TIMEOUT_SEC,
            )

        _print_json("DECISION CHAIN (e2e_pipeline_forced)", chain)
        assert chain["verdict"] is not None
        assert chain["execution"] is not None
        assert chain["audit"] is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_e2e_analyst_live() -> None:
    """
    Live Analyst: real MCP smoke + funding_flip event → persisted Proposal (any action).

    action=none is a valid pass — logs the outcome; does not require a trade.
    """
    async with _e2e_runtime() as (settings, bus, store, tasks):
        await store.set_strategy(
            text=ANALYST_STRATEGY_TEXT,
            max_notional_usd=500.0,
            max_leverage=3.0,
            max_daily_loss_usd=500.0,
            allowed_markets=["BTC", "ETH", "INJ"],
        )

        mcp = await _install_mcp_singleton(settings)
        await _mcp_smoke(mcp, settings.injective_wallet_address)

        tasks.extend(await _start_agents(bus, store, settings, LIVE_AGENTS))

        event = MarketEvent(
            id=str(uuid.uuid4()),
            ts=datetime.now(timezone.utc),
            kind="funding_flip",
            market="BTC",
            payload=FUNDING_FLIP_PAYLOAD,
            source="simulator",
        )
        await inject_event(bus, store, event)
        print(f"\nInjected funding_flip event id={event.id} market=BTC")

        chain = await _wait_for_proposal(
            store,
            event.id,
            timeout_sec=ANALYST_PIPELINE_TIMEOUT_SEC,
        )

        proposal = chain["proposal"]
        assert proposal is not None
        action = proposal.get("action")
        print(
            f"\nAnalyst proposal: id={proposal.get('id')} action={action!r} "
            f"market={proposal.get('market')!r} confidence={proposal.get('confidence')}"
        )
        _print_json("DECISION CHAIN (e2e_analyst_live — partial)", chain)

        assert action in ("open", "close", "adjust", "none")
        assert proposal.get("event_id") == event.id
        assert proposal.get("reasoning")
