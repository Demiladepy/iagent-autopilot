"""Executor agent — the only agent that invokes MCP write-tools."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sentinel.agents.resilience import log_agent_loop_error
from sentinel.bus import TOPIC_EXECUTION, TOPIC_VERDICT
from sentinel.mcp_client import (
    MCP_WRITE_TOOLS,
    MCPError,
    InjectiveMCPClient,
    get_mcp_client,
    scrub_secrets,
)
from sentinel.schemas import Execution

if TYPE_CHECKING:
    from sentinel.bus import EventBus
    from sentinel.config import Settings
    from sentinel.store import SentinelStore

logger = logging.getLogger(__name__)
AGENT_NAME = "executor"

_market_cache: dict[str, dict[str, str]] = {}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _extract_tx_hash(result: Any) -> str | None:
    if not isinstance(result, dict):
        return None
    for key in ("txHash", "tx_hash", "hash"):
        if result.get(key):
            return str(result[key])
    return None


async def _guarded_mcp_call(
    mcp: InjectiveMCPClient,
    config: "Settings",
    tool: str,
    args: dict[str, Any],
) -> Any:
    """Route MCP calls; block write tools when DRY_RUN is enabled."""
    if tool in MCP_WRITE_TOOLS and config.dry_run:
        logger.info("[DRY_RUN] would call %s %s", tool, scrub_secrets(args))
        return {"dry_run": True, "tool": tool, "args": scrub_secrets(args)}
    return await mcp.call(tool, args)


async def _resolve_market(
    mcp: InjectiveMCPClient,
    config: "Settings",
    market: str,
) -> tuple[str, str]:
    key = market.upper()
    if key in _market_cache:
        cached = _market_cache[key]
        return cached["symbol"], cached["ticker"]

    raw = await _guarded_mcp_call(mcp, config, "market_list", {})
    markets = raw if isinstance(raw, list) else []
    target_ticker = f"{key}/USDT PERP"

    for entry in markets:
        if not isinstance(entry, dict):
            continue
        sym = str(entry.get("symbol", "")).upper()
        ticker = str(entry.get("ticker", ""))
        if sym == key or ticker.upper() == target_ticker.upper():
            resolved = {"symbol": entry.get("symbol", key), "ticker": ticker or target_ticker}
            _market_cache[key] = resolved
            return resolved["symbol"], resolved["ticker"]

    resolved = {"symbol": key, "ticker": target_ticker}
    _market_cache[key] = resolved
    logger.warning("market_list miss for %s — using %s", key, target_ticker)
    return key, target_ticker


def _trade_open_args(
    config: "Settings",
    *,
    symbol: str,
    side: str,
    notional: float,
    leverage: float | None,
) -> dict[str, Any]:
    args: dict[str, Any] = {
        "address": config.injective_wallet_address,
        "password": config.injective_wallet_password,
        "symbol": symbol,
        "side": side,
        "amount": str(notional),
    }
    if leverage is not None and leverage > 0:
        args["leverage"] = int(leverage)
    return args


def _trade_close_args(
    config: "Settings",
    *,
    symbol: str,
) -> dict[str, Any]:
    return {
        "address": config.injective_wallet_address,
        "password": config.injective_wallet_password,
        "symbol": symbol,
    }


def _demo_transfer_send_args(
    config: "Settings",
    *,
    recipient: str,
    denom: str,
    amount: str,
) -> dict[str, Any]:
    # Use the MCP tool's inputSchema (discovered from tools/list):
    # required: address, password, recipient, denom, amount
    return {
        "address": config.injective_wallet_address,
        "password": config.injective_wallet_password,
        "recipient": recipient,
        "denom": denom,
        "amount": amount,
    }


async def _publish_execution(
    *,
    bus: "EventBus",
    store: "SentinelStore",
    execution: Execution,
) -> None:
    await store.save_execution(execution)
    await bus.publish(TOPIC_EXECUTION, execution.model_dump(mode="json"))


async def _record_skipped(
    *,
    bus: "EventBus",
    store: "SentinelStore",
    proposal_id: str,
    reason: str,
) -> None:
    execution = Execution(
        id=str(uuid.uuid4()),
        proposal_id=proposal_id,
        ts=_utc_now(),
        status="skipped",
        tx_hash=None,
        tool_called=None,
        tool_args=None,
        tool_result=None,
        error=reason,
    )
    await _publish_execution(bus=bus, store=store, execution=execution)
    logger.info("EXECUTOR SKIP proposal_id=%s reason=%s", proposal_id, reason)


async def _record_failed(
    *,
    bus: "EventBus",
    store: "SentinelStore",
    proposal_id: str,
    tool_called: str | None,
    tool_args: dict[str, Any] | None,
    error: str,
) -> None:
    execution = Execution(
        id=str(uuid.uuid4()),
        proposal_id=proposal_id,
        ts=_utc_now(),
        status="failed",
        tx_hash=None,
        tool_called=tool_called,
        tool_args=tool_args,
        tool_result=None,
        error=error,
    )
    await _publish_execution(bus=bus, store=store, execution=execution)
    logger.error(
        "EXECUTOR FAILED proposal_id=%s tool=%s error=%s",
        proposal_id,
        tool_called,
        error,
    )


async def _record_success(
    *,
    bus: "EventBus",
    store: "SentinelStore",
    proposal_id: str,
    tool_called: str,
    tool_args: dict[str, Any] | None,
    tool_result: Any,
    journal_lesson: str,
    is_close: bool = False,
    tx_hash: str | None = None,
) -> None:
    resolved_tx = tx_hash or _extract_tx_hash(tool_result)
    now = _utc_now()
    execution = Execution(
        id=str(uuid.uuid4()),
        proposal_id=proposal_id,
        ts=now,
        status="success",
        tx_hash=resolved_tx,
        tool_called=tool_called,
        tool_args=tool_args,
        tool_result=tool_result if isinstance(tool_result, dict) else {"result": tool_result},
        error=None,
    )
    await _publish_execution(bus=bus, store=store, execution=execution)
    if is_close:
        await store.save_journal_entry(
            execution_id=execution.id,
            opened_at=None,
            closed_at=now,
            pnl_usd=None,
            lesson=journal_lesson,
        )
    else:
        await store.save_journal_entry(
            execution_id=execution.id,
            opened_at=now,
            closed_at=None,
            pnl_usd=0.0,
            lesson=journal_lesson,
        )
    logger.info(
        "EXECUTOR SUCCESS proposal_id=%s tool=%s tx_hash=%s %s",
        proposal_id,
        tool_called,
        resolved_tx or "(none)",
        journal_lesson[:120],
    )


async def _record_dry_run_bundle(
    *,
    bus: "EventBus",
    store: "SentinelStore",
    proposal_id: str,
    tool_called: str,
    tool_args: dict[str, Any],
    journal_lesson: str,
) -> None:
    dry_id = str(uuid.uuid4())
    await _record_success(
        bus=bus,
        store=store,
        proposal_id=proposal_id,
        tool_called=tool_called,
        tool_args=scrub_secrets(tool_args),
        tool_result={"dry_run": True, "tool": tool_called},
        journal_lesson=journal_lesson,
        tx_hash=f"dry-run-{dry_id}",
    )


async def _execute_open(
    mcp: InjectiveMCPClient,
    config: "Settings",
    proposal: dict[str, Any],
    verdict: dict[str, Any],
) -> tuple[str, dict[str, Any], Any]:
    market = str(proposal.get("market") or "BTC").upper()
    side = str(proposal.get("side") or "long").lower()
    notional = _safe_float(
        verdict.get("modified_notional") or proposal.get("notional_usd"),
    )
    leverage = verdict.get("modified_leverage") or proposal.get("leverage")
    if leverage is not None:
        leverage = _safe_float(leverage)

    symbol, ticker = await _resolve_market(mcp, config, market)
    args = _trade_open_args(
        config,
        symbol=symbol,
        side=side,
        notional=notional,
        leverage=leverage,
    )
    logger.info(
        "EXECUTOR trade_open market=%s ticker=%s side=%s notional=%s leverage=%s",
        market,
        ticker,
        side,
        notional,
        leverage,
    )
    result = await _guarded_mcp_call(mcp, config, "trade_open", args)
    return "trade_open", {**args, "ticker": ticker, "market": market}, result


async def _execute_demo_real_tx_transfer(
    mcp: InjectiveMCPClient,
    config: "Settings",
) -> tuple[str, dict[str, Any], Any]:
    """
    Demo-only on-chain proof-of-execution.

    Substitute a tiny bank-level transfer for a perp trade, to produce a real,
    explorer-verifiable Injective testnet tx.
    """
    sender = config.injective_wallet_address
    recipient = (config.demo_tx_recipient or "").strip()
    if not recipient:
        # NOTE: the MCP server's transfer tool blocks self-transfers.
        # We require an explicit recipient to avoid silently failing the demo.
        raise MCPError(
            "DEMO_TX_RECIPIENT is required for DEMO_REAL_TX. "
            "The MCP transfer_send tool blocks self-transfers; set DEMO_TX_RECIPIENT "
            "to a different inj1... address (can be another wallet you control)."
        )
    if recipient == sender:
        raise MCPError(
            "DEMO_TX_RECIPIENT cannot equal the sender address. "
            "The MCP transfer_send tool blocks self-transfers."
        )

    # USDT denom on Injective testnet (peggy USDT). Keep configurable later if needed.
    usdt_denom = "peggy0x87aB3B4C8661e07D6372361211B96ed4Dc36B1B5"
    amount = str(config.demo_tx_amount or "0.1").strip() or "0.1"
    args = _demo_transfer_send_args(
        config,
        recipient=recipient,
        denom=usdt_denom,
        amount=amount,
    )
    logger.info("[DEMO REAL TX] proof-of-execution transfer_send %s", scrub_secrets(args))
    result = await _guarded_mcp_call(mcp, config, "transfer_send", args)
    return "transfer_send", args, result


async def _execute_close(
    mcp: InjectiveMCPClient,
    config: "Settings",
    proposal: dict[str, Any],
) -> tuple[str, dict[str, Any], Any]:
    market = str(proposal.get("market") or "BTC").upper()
    symbol, ticker = await _resolve_market(mcp, config, market)
    args = _trade_close_args(config, symbol=symbol)
    logger.info("EXECUTOR trade_close market=%s ticker=%s", market, ticker)
    result = await _guarded_mcp_call(mcp, config, "trade_close", args)
    return "trade_close", {**args, "ticker": ticker, "market": market}, result


async def _execute_adjust(
    mcp: InjectiveMCPClient,
    config: "Settings",
    proposal: dict[str, Any],
    verdict: dict[str, Any],
) -> tuple[str, dict[str, Any], Any]:
    close_tool, close_args, close_result = await _execute_close(mcp, config, proposal)
    open_tool, open_args, open_result = await _execute_open(mcp, config, proposal, verdict)
    return (
        "trade_adjust",
        {"close": close_args, "open": open_args},
        {"close": close_result, "open": open_result},
    )


async def _process_verdict(
    *,
    bus: "EventBus",
    store: "SentinelStore",
    config: "Settings",
    verdict_msg: dict[str, Any],
) -> None:
    proposal_id = str(verdict_msg.get("proposal_id", ""))
    if not proposal_id:
        logger.warning("EXECUTOR verdict missing proposal_id")
        return

    prior = await store.get_execution_for_proposal(proposal_id)
    if prior and prior.get("status") == "success":
        logger.info(
            "EXECUTOR idempotent skip — proposal_id=%s already executed (execution_id=%s)",
            proposal_id,
            prior.get("id"),
        )
        return

    if not verdict_msg.get("approved"):
        await _record_skipped(
            bus=bus,
            store=store,
            proposal_id=proposal_id,
            reason="verdict_not_approved",
        )
        return

    proposal = await store.get_proposal(proposal_id)
    if not proposal:
        proposal = verdict_msg.get("proposal") or {}
    if not proposal:
        await _record_skipped(
            bus=bus,
            store=store,
            proposal_id=proposal_id,
            reason="proposal_not_found",
        )
        return

    action = proposal.get("action", "none")
    logger.info(
        "EXECUTOR action=%r demo_real_tx=%s dry_run=%s",
        action,
        config.demo_real_tx,
        config.dry_run,
    )
    if action == "none":
        await _record_skipped(
            bus=bus,
            store=store,
            proposal_id=proposal_id,
            reason="action_none",
        )
        return

    if not config.injective_wallet_address or not config.injective_wallet_password:
        await _record_skipped(
            bus=bus,
            store=store,
            proposal_id=proposal_id,
            reason="wallet_not_configured",
        )
        return

    market = str(proposal.get("market", "?"))
    side = str(proposal.get("side", "?"))
    notional = verdict_msg.get("modified_notional") or proposal.get("notional_usd")

    mcp = await get_mcp_client(config)
    if mcp is None or not mcp.is_healthy():
        if config.dry_run:
            mcp = None
        else:
            await _record_failed(
                bus=bus,
                store=store,
                proposal_id=proposal_id,
                tool_called=None,
                tool_args=None,
                error="mcp_unavailable — set MCP_SERVER_PATH or restart after MCP crash",
            )
            return

    tool_called: str | None = None
    tool_args: dict[str, Any] | None = None

    try:
        if action == "open":
            if config.demo_real_tx and not config.dry_run:
                logger.info("EXECUTOR open branch: demo_real_tx transfer_send")
                assert mcp is not None
                tool_called, tool_args, result = await _execute_demo_real_tx_transfer(mcp, config)
                await _record_success(
                    bus=bus,
                    store=store,
                    proposal_id=proposal_id,
                    tool_called=tool_called,
                    tool_args=scrub_secrets(tool_args or {}),
                    tool_result=result,
                    journal_lesson=f"[demo-real-tx] proof-of-execution transfer for proposal {proposal_id}",
                )
                return
            if config.dry_run:
                logger.info("EXECUTOR open branch: dry_run trade_open")
                symbol, _ = await _resolve_market(mcp, config, market) if mcp else (market, "")
                tool_args = _trade_open_args(
                    config,
                    symbol=symbol,
                    side=str(proposal.get("side") or "long").lower(),
                    notional=_safe_float(notional),
                    leverage=verdict_msg.get("modified_leverage") or proposal.get("leverage"),
                )
                await _record_dry_run_bundle(
                    bus=bus,
                    store=store,
                    proposal_id=proposal_id,
                    tool_called="trade_open",
                    tool_args=tool_args,
                    journal_lesson=f"[dry-run] open {side} {market} ${notional}",
                )
                return
            logger.info("EXECUTOR open branch: live trade_open")
            assert mcp is not None
            tool_called, tool_args, result = await _execute_open(
                mcp, config, proposal, verdict_msg
            )
            journal = f"Opened {side} {market} ${notional}"
            await _record_success(
                bus=bus,
                store=store,
                proposal_id=proposal_id,
                tool_called=tool_called,
                tool_args=tool_args,
                tool_result=result,
                journal_lesson=journal,
            )
        elif action == "close":
            if config.dry_run:
                symbol, _ = await _resolve_market(mcp, config, market) if mcp else (market, "")
                tool_args = _trade_close_args(config, symbol=symbol)
                await _record_dry_run_bundle(
                    bus=bus,
                    store=store,
                    proposal_id=proposal_id,
                    tool_called="trade_close",
                    tool_args=tool_args,
                    journal_lesson=f"[dry-run] close {side} {market}",
                )
                return
            assert mcp is not None
            tool_called, tool_args, result = await _execute_close(mcp, config, proposal)
            journal = f"Closed {side} {market}"
            await _record_success(
                bus=bus,
                store=store,
                proposal_id=proposal_id,
                tool_called=tool_called,
                tool_args=tool_args,
                tool_result=result,
                journal_lesson=journal,
                is_close=True,
            )
        elif action == "adjust":
            if config.dry_run:
                symbol, _ = await _resolve_market(mcp, config, market) if mcp else (market, "")
                close_args = _trade_close_args(config, symbol=symbol)
                open_args = _trade_open_args(
                    config,
                    symbol=symbol,
                    side=str(proposal.get("side") or "long").lower(),
                    notional=_safe_float(notional),
                    leverage=verdict_msg.get("modified_leverage") or proposal.get("leverage"),
                )
                logger.info("[DRY_RUN] would call trade_close %s", scrub_secrets(close_args))
                logger.info("[DRY_RUN] would call trade_open %s", scrub_secrets(open_args))
                await _record_dry_run_bundle(
                    bus=bus,
                    store=store,
                    proposal_id=proposal_id,
                    tool_called="trade_adjust",
                    tool_args={"close": close_args, "open": open_args},
                    journal_lesson=f"[dry-run] adjust {side} {market} ${notional}",
                )
                return
            assert mcp is not None
            tool_called, tool_args, result = await _execute_adjust(
                mcp, config, proposal, verdict_msg
            )
            journal = f"Adjusted {side} {market} to ${notional}"
            await _record_success(
                bus=bus,
                store=store,
                proposal_id=proposal_id,
                tool_called=tool_called,
                tool_args=tool_args,
                tool_result=result,
                journal_lesson=journal,
            )
        else:
            await _record_skipped(
                bus=bus,
                store=store,
                proposal_id=proposal_id,
                reason=f"unknown_action:{action}",
            )

    except (MCPError, Exception) as exc:
        await _record_failed(
            bus=bus,
            store=store,
            proposal_id=proposal_id,
            tool_called=tool_called,
            tool_args=tool_args,
            error=str(exc),
        )


async def run(
    *,
    bus: "EventBus",
    store: "SentinelStore",
    config: "Settings",
) -> None:
    await bus.publish("agent.status", {"agent": AGENT_NAME, "status": "running"})
    logger.info(
        "Executor started DEMO_REAL_TX=%s DRY_RUN=%s simulator=%s network=%s",
        config.demo_real_tx,
        config.dry_run,
        config.simulator_mode,
        config.injective_network,
    )
    try:
        async for msg in bus.subscribe(TOPIC_VERDICT):
            try:
                await _process_verdict(
                    bus=bus, store=store, config=config, verdict_msg=msg
                )
            except Exception as exc:
                log_agent_loop_error(AGENT_NAME, exc, context="verdict")
    except asyncio.CancelledError:
        await bus.publish("agent.status", {"agent": AGENT_NAME, "status": "stopped"})
        logger.info("Executor stopped")
        raise
