"""Risk agent — deterministic gatekeeper + fast Groq sanity check."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sentinel.agents.resilience import log_agent_loop_error
from sentinel.bus import TOPIC_PROPOSAL, TOPIC_VERDICT
from sentinel.llm import groq_client
from sentinel.mcp_client import get_mcp_client
from sentinel.schemas import RiskVerdict

if TYPE_CHECKING:
    from sentinel.bus import EventBus
    from sentinel.config import Settings
    from sentinel.store import SentinelStore

logger = logging.getLogger(__name__)
AGENT_NAME = "risk"

RISK_SYSTEM_PROMPT = """You are the Risk agent in iAgent Autopilot. You veto trades that look reckless even if they pass deterministic limits. Reply with ONLY "APPROVE" or "REJECT: <one-sentence reason>". Be conservative. If anything looks unusual — wrong-way during a fast move, oversized vs balance, contradicts the journal — reject. The Analyst is creative; you are the brake."""

CONFIDENCE_FLOOR = 0.4

# Daily halt after max loss breach (UTC date string)
_trading_halted_date: str | None = None


@dataclass
class DeterministicResult:
    approved: bool
    reasons: list[str] = field(default_factory=list)
    modified_notional: float | None = None
    modified_leverage: float | None = None
    hard_reject: bool = False


def _utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _extract_available_balance(balances: Any) -> float:
    if not isinstance(balances, dict):
        return 0.0
    total = 0.0
    for entry in balances.get("subaccount") or []:
        if not isinstance(entry, dict):
            continue
        sym = str(entry.get("symbol", "")).upper()
        if sym in ("USDT", "USD", "USDC") or "USD" in sym:
            total += _safe_float(entry.get("available"))
    if total > 0:
        return total
    for entry in balances.get("bank") or []:
        if not isinstance(entry, dict):
            continue
        sym = str(entry.get("symbol", "")).upper()
        if sym in ("USDT", "USD", "USDC") or "USD" in sym:
            total += _safe_float(entry.get("amount"))
    return total


def _normalize_positions(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [p for p in raw if isinstance(p, dict)]
    return []


def _has_opposing_position(
    positions: list[dict[str, Any]],
    market: str | None,
    side: str | None,
) -> bool:
    if not market or not side:
        return False
    market_u = market.upper()
    side_l = side.lower()
    for pos in positions:
        sym = str(pos.get("symbol", "")).upper()
        pos_side = str(pos.get("side", "")).lower()
        if sym != market_u or not pos_side:
            continue
        if pos_side != side_l:
            return True
    return False


async def _fetch_mcp_context(config: "Settings") -> tuple[list[dict[str, Any]], Any]:
    if not config.injective_wallet_address:
        return [], {"bank": [], "subaccount": []}
    mcp = await get_mcp_client(config)
    if mcp is None or not mcp.is_healthy():
        return [], {"bank": [], "subaccount": []}
    address = config.injective_wallet_address
    results = await asyncio.gather(
        mcp.call("account_positions", {"address": address}),
        mcp.call("account_balances", {"address": address}),
        return_exceptions=True,
    )
    positions: list[dict[str, Any]] = []
    balances: Any = {"bank": [], "subaccount": []}
    if not isinstance(results[0], BaseException):
        positions = _normalize_positions(results[0])
    if not isinstance(results[1], BaseException):
        balances = results[1] if results[1] is not None else balances
    return positions, balances


def _run_deterministic_checks(
    proposal: dict[str, Any],
    *,
    strategy: dict[str, Any],
    today_pnl: float,
    positions: list[dict[str, Any]],
    kill_switch: bool,
) -> DeterministicResult:
    global _trading_halted_date

    reasons: list[str] = []
    max_notional = float(strategy.get("max_notional_usd", 1000))
    max_leverage = float(strategy.get("max_leverage", 10))
    max_daily_loss = float(strategy.get("max_daily_loss_usd", 500))
    allowed = {m.upper() for m in strategy.get("allowed_markets", ["BTC", "ETH", "INJ"])}

    action = proposal.get("action", "none")
    modified_notional = proposal.get("notional_usd")
    modified_leverage = proposal.get("leverage")

    # (a) Kill switch
    if kill_switch:
        return DeterministicResult(False, ["kill_switch_active"], hard_reject=True)

    # Daily halt latch
    if _trading_halted_date == _utc_date():
        return DeterministicResult(False, ["daily_loss_halt_active"], hard_reject=True)

    # (b) No action — auto-approve
    if action == "none":
        return DeterministicResult(True, ["no_action_pass"])

    # (c) Daily loss halt
    if today_pnl <= -max_daily_loss:
        _trading_halted_date = _utc_date()
        return DeterministicResult(
            False,
            [f"daily_loss_limit_hit: today_pnl={today_pnl:.2f} limit=-{max_daily_loss:.2f}"],
            hard_reject=True,
        )

    # (d) Notional cap — modify down
    if modified_notional is not None:
        notional = float(modified_notional)
        if notional > max_notional:
            modified_notional = max_notional
            reasons.append(f"notional_capped_to_{max_notional}")

    # (e) Leverage cap — modify down
    if modified_leverage is not None:
        lev = float(modified_leverage)
        if lev > max_leverage:
            modified_leverage = max_leverage
            reasons.append(f"leverage_capped_to_{max_leverage}")

    # (f) Allowed markets
    market = proposal.get("market")
    if market and allowed and str(market).upper() not in allowed:
        return DeterministicResult(False, [f"market_not_allowed: {market}"], hard_reject=True)

    # (g) Confidence floor
    confidence = float(proposal.get("confidence", 0))
    if confidence < CONFIDENCE_FLOOR:
        return DeterministicResult(
            False,
            [f"confidence_below_floor: {confidence:.2f}"],
            hard_reject=True,
        )

    # (h) Opposing position
    side = proposal.get("side")
    if _has_opposing_position(positions, market, side) and action != "close":
        return DeterministicResult(
            False,
            [f"opposing_position_exists: {market} {side} vs open book"],
            hard_reject=True,
        )

    return DeterministicResult(
        True,
        reasons or ["deterministic_pass"],
        modified_notional=modified_notional,
        modified_leverage=modified_leverage,
    )


def _build_groq_user_prompt(
    proposal: dict[str, Any],
    positions: list[dict[str, Any]],
    available_balance: float,
    journal: list[dict[str, Any]],
) -> str:
    return f"""Proposal: {json.dumps(proposal, indent=2, default=str)}
Positions: {json.dumps(positions, indent=2, default=str)}
Balance: ${available_balance:.2f}
Recent journal: {json.dumps(journal, indent=2, default=str)}

APPROVE or REJECT?"""


async def _process_proposal(
    *,
    bus: "EventBus",
    store: "SentinelStore",
    config: "Settings",
    proposal_msg: dict[str, Any],
) -> None:
    started = time.perf_counter()
    proposal_id = str(proposal_msg.get("id", ""))
    if not proposal_id:
        logger.warning("Risk skipping proposal without id")
        return

    strategy, today_pnl, journal, (positions, balances) = await asyncio.gather(
        store.get_strategy(),
        store.today_pnl(),
        store.recent_journal(10),
        _fetch_mcp_context(config),
    )

    kill_active = config.kill_switch or store.kill_switch_active
    det = _run_deterministic_checks(
        proposal_msg,
        strategy=strategy,
        today_pnl=today_pnl,
        positions=positions,
        kill_switch=kill_active,
    )

    approved = det.approved
    reasons = list(det.reasons)

    if approved and not det.hard_reject and proposal_msg.get("action") != "none":
        user_prompt = _build_groq_user_prompt(
            proposal_msg,
            positions,
            _extract_available_balance(balances),
            journal,
        )
        groq_ok, groq_reason, groq_ms = await groq_client.risk_sanity_check(
            config, RISK_SYSTEM_PROMPT, user_prompt
        )
        reasons.append(groq_reason)
        if not groq_ok:
            approved = False

    verdict = RiskVerdict(
        proposal_id=proposal_id,
        ts=datetime.now(timezone.utc),
        approved=approved,
        reasons=reasons,
        modified_notional=det.modified_notional if approved else None,
        modified_leverage=det.modified_leverage if approved else None,
    )

    await store.save_verdict(verdict)
    await bus.publish(
        TOPIC_VERDICT,
        {**verdict.model_dump(mode="json"), "proposal": proposal_msg},
    )

    elapsed_ms = (time.perf_counter() - started) * 1000
    logger.info(
        "Risk verdict proposal_id=%s approved=%s reasons=%s latency_ms=%.1f",
        proposal_id,
        approved,
        reasons,
        elapsed_ms,
    )


async def run(
    *,
    bus: "EventBus",
    store: "SentinelStore",
    config: "Settings",
) -> None:
    await bus.publish("agent.status", {"agent": AGENT_NAME, "status": "running"})
    logger.info("Risk agent started")
    try:
        async for msg in bus.subscribe(TOPIC_PROPOSAL):
            try:
                await _process_proposal(
                    bus=bus, store=store, config=config, proposal_msg=msg
                )
            except Exception as exc:
                log_agent_loop_error(AGENT_NAME, exc, context="proposal")
    except asyncio.CancelledError:
        await bus.publish("agent.status", {"agent": AGENT_NAME, "status": "stopped"})
        raise
