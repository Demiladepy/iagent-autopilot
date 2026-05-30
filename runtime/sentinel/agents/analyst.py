"""Analyst agent — consumes MarketEvents, produces Proposals via Claude."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from sentinel.agents.resilience import log_agent_loop_error
from sentinel.bus import TOPIC_EVENT, TOPIC_PROPOSAL
from sentinel.llm import anthropic_client
from sentinel.mcp_client import get_mcp_client
from sentinel.schemas import MarketEvent, Proposal, ProposalOutput

if TYPE_CHECKING:
    from sentinel.bus import EventBus
    from sentinel.config import Settings
    from sentinel.store import SentinelStore

logger = logging.getLogger(__name__)
AGENT_NAME = "analyst"

SAFE_DEFAULT_PROPOSAL = ProposalOutput(
    action="none",
    market=None,
    side=None,
    notional_usd=None,
    leverage=None,
    reasoning="Analyst could not validate LLM output; defaulting to no action.",
    confidence=0.0,
    expected_hold_hours=None,
    invalidation=None,
)

SYSTEM_PROMPT = """You are the Analyst agent in iAgent Autopilot, an autonomous trading system on Injective.

Your job: receive market events and decide whether to propose a trading action. You do NOT execute trades. You produce structured proposals. A separate Risk agent will gate them. An Executor will perform them. An Auditor will explain them later.

RULES:
1. "No action" is always a valid output. A forced trade is worse than no trade.
2. Reason explicitly. Your rationale will be shown to the user verbatim. Write it like you're explaining to a thoughtful junior trader.
3. Never override user strategy. If they say "max 3x leverage" and you want 5x, the answer is 3x or no trade.
4. Reference history. If the journal shows a similar setup failed recently, weigh that.
5. The `invalidation` field is mandatory for any non-"none" action — one sentence stating what would make this trade wrong. The Auditor will check it later.
6. Output ONLY valid JSON matching the schema. No prose outside JSON.

OUTPUT SCHEMA:
{
  "action": "open" | "close" | "adjust" | "none",
  "market": "BTC" | "ETH" | "INJ" | null,
  "side": "long" | "short" | null,
  "notional_usd": number | null,
  "leverage": number | null,
  "reasoning": "1-3 sentences in plain English",
  "confidence": 0.0 to 1.0,
  "expected_hold_hours": number | null,
  "invalidation": "1 sentence: what makes this trade wrong" or null
}"""


def _build_user_prompt(
    *,
    event: dict[str, Any],
    strategy: dict[str, Any],
    positions: Any,
    balances: Any,
    journal: list[dict[str, Any]],
    today_pnl: float,
) -> str:
    allowed = strategy.get("allowed_markets", ["BTC", "ETH", "INJ"])
    if isinstance(allowed, list):
        allowed_str = ", ".join(allowed)
    else:
        allowed_str = str(allowed)

    return f"""EVENT:
{json.dumps(event, indent=2, default=str)}

USER STRATEGY (their own words):
{strategy.get("text", "") or "(no strategy text set)"}

HARD LIMITS:
- Max notional per trade: ${strategy.get("max_notional_usd", 1000)}
- Max leverage: {strategy.get("max_leverage", 10)}x
- Allowed markets: {allowed_str}
- Today's PnL so far: ${today_pnl:.2f}
- Max daily loss before halt: ${strategy.get("max_daily_loss_usd", 500)}

CURRENT POSITIONS:
{json.dumps(positions, indent=2, default=str)}

CURRENT BALANCES:
{json.dumps(balances, indent=2, default=str)}

RECENT TRADE JOURNAL (most recent first):
{json.dumps(journal, indent=2, default=str)}

Produce your proposal as JSON."""


async def _fetch_account_context(
    config: "Settings",
) -> tuple[Any, Any]:
    """Return (positions, balances); empty when MCP/wallet unavailable."""
    if not config.injective_wallet_address:
        return [], {"bank": [], "subaccount": []}

    mcp = await get_mcp_client(config)
    if mcp is None or not mcp.is_healthy():
        return [], {"bank": [], "subaccount": []}

    address = config.injective_wallet_address
    positions_coro = mcp.call("account_positions", {"address": address})
    balances_coro = mcp.call("account_balances", {"address": address})
    results = await asyncio.gather(positions_coro, balances_coro, return_exceptions=True)

    positions: Any = []
    balances: Any = {"bank": [], "subaccount": []}
    if not isinstance(results[0], BaseException):
        positions = results[0] if results[0] is not None else []
    else:
        logger.warning("account_positions failed: %s", results[0])
    if not isinstance(results[1], BaseException):
        balances = results[1] if results[1] is not None else balances
    else:
        logger.warning("account_balances failed: %s", results[1])
    return positions, balances


async def _call_claude_with_retry(
    config: "Settings",
    user_prompt: str,
) -> ProposalOutput:
    retry_hint = (
        "Your previous response failed schema validation. "
        "Fix your output to match the JSON schema exactly. "
        "Ensure invalidation is a non-empty string for any action other than 'none'. "
        "Output ONLY valid JSON."
    )
    last_error: str | None = None
    for attempt in range(2):
        try:
            result = await anthropic_client.generate_proposal(
                config,
                SYSTEM_PROMPT,
                user_prompt,
                retry_hint=retry_hint if attempt == 1 else None,
            )
            parsed = result.parsed
            ProposalOutput.model_validate(parsed.model_dump())
            return parsed
        except (ValidationError, json.JSONDecodeError, TypeError, ValueError, StopAsyncIteration) as exc:
            last_error = str(exc)
            logger.warning(
                "Analyst proposal validation failed (attempt %d): %s",
                attempt + 1,
                last_error,
            )
    logger.error(
        "Analyst LLM output invalid after retry — emitting safe default action=none: %s",
        last_error,
    )
    return SAFE_DEFAULT_PROPOSAL.model_copy(
        update={
            "reasoning": (
                f"{SAFE_DEFAULT_PROPOSAL.reasoning} Last error: {last_error}"
            ),
        }
    )


def _clamp_to_strategy(output: ProposalOutput, strategy: dict[str, Any]) -> ProposalOutput:
    """Enforce hard limits from strategy on model output."""
    max_notional = float(strategy.get("max_notional_usd", 1000))
    max_leverage = float(strategy.get("max_leverage", 10))
    allowed = {m.upper() for m in strategy.get("allowed_markets", [])}

    updates: dict[str, Any] = {}
    if output.notional_usd is not None:
        updates["notional_usd"] = min(output.notional_usd, max_notional)
    if output.leverage is not None:
        updates["leverage"] = min(output.leverage, max_leverage)
    if output.market and allowed and output.market.upper() not in allowed:
        updates["action"] = "none"
        updates["market"] = None
        updates["side"] = None
        updates["notional_usd"] = None
        updates["leverage"] = None
        updates["invalidation"] = None
        updates["reasoning"] = (
            output.reasoning
            + f" (Overridden to none: {output.market} not in allowed markets.)"
        )
    if updates:
        return output.model_copy(update=updates)
    return output


async def _process_event(
    *,
    bus: "EventBus",
    store: "SentinelStore",
    config: "Settings",
    msg: dict[str, Any],
) -> None:
    event_id = str(msg.get("id", ""))
    if not event_id:
        logger.warning("Analyst skipping event without id")
        return
    if await store.has_proposal_for_event(event_id):
        logger.debug("Analyst skipping already-analyzed event_id=%s", event_id)
        return

    try:
        event = MarketEvent.model_validate({k: v for k, v in msg.items() if k != "topic"})
        event_json = event.model_dump(mode="json")
    except ValidationError:
        event_json = {k: v for k, v in msg.items() if k != "topic"}

    strategy = await store.get_strategy()
    positions, balances = await _fetch_account_context(config)
    journal = await store.recent_journal(10)
    today_pnl = await store.today_pnl()

    user_prompt = _build_user_prompt(
        event=event_json,
        strategy=strategy,
        positions=positions,
        balances=balances,
        journal=journal,
        today_pnl=today_pnl,
    )

    output = await _call_claude_with_retry(config, user_prompt)
    output = _clamp_to_strategy(output, strategy)

    market = output.market or msg.get("market")
    if market:
        market = str(market).upper()

    proposal = Proposal(
        id=str(uuid.uuid4()),
        event_id=event_id,
        ts=datetime.now(timezone.utc),
        action=output.action,
        market=market,
        side=output.side,
        notional_usd=output.notional_usd,
        leverage=output.leverage,
        reasoning=output.reasoning,
        confidence=output.confidence,
        expected_hold_hours=output.expected_hold_hours,
        invalidation=output.invalidation,
    )

    await store.save_proposal(proposal)
    await bus.publish(TOPIC_PROPOSAL, proposal.model_dump(mode="json"))
    logger.info(
        "Analyst proposal id=%s event_id=%s action=%s market=%s confidence=%.2f",
        proposal.id,
        proposal.event_id,
        proposal.action,
        proposal.market,
        proposal.confidence,
    )


async def run(
    *,
    bus: "EventBus",
    store: "SentinelStore",
    config: "Settings",
) -> None:
    await bus.publish("agent.status", {"agent": AGENT_NAME, "status": "running"})
    logger.info("Analyst started")
    try:
        async for msg in bus.subscribe(TOPIC_EVENT):
            if config.kill_switch or store.kill_switch_active:
                continue
            try:
                await _process_event(bus=bus, store=store, config=config, msg=msg)
            except Exception as exc:
                log_agent_loop_error(AGENT_NAME, exc, context="event")
    except asyncio.CancelledError:
        await bus.publish("agent.status", {"agent": AGENT_NAME, "status": "stopped"})
        raise
