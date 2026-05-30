"""Auditor agent — plain-English post-execution explanations via Claude."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sentinel.agents.resilience import log_agent_loop_error
from sentinel.bus import TOPIC_AUDIT, TOPIC_AUDIT_STREAM, TOPIC_EXECUTION
from sentinel.llm import anthropic_client
from sentinel.mcp_client import get_mcp_client
from sentinel.schemas import AuditNote

if TYPE_CHECKING:
    from sentinel.bus import EventBus
    from sentinel.config import Settings
    from sentinel.store import SentinelStore

logger = logging.getLogger(__name__)
AGENT_NAME = "auditor"

AUDIT_SYSTEM_PROMPT = """You are the Auditor in iAgent Autopilot. Your job is to explain — in 3-5 sentences of plain English — what just happened and why. Write for a smart user who wants to trust the system but verify every decision.

Structure your output:
1. One sentence: what triggered this.
2. One sentence: what the Analyst proposed and why.
3. One sentence: how Risk evaluated it.
4. One sentence: what was actually executed (or skipped, and why).
5. (Optional) One sentence flagging anything unusual the user should know.

Be honest. If the Analyst's reasoning was thin, say so. If Risk modified the size, say so. If the trade was skipped, explain why.

After your summary, output a JSON object on a new line:
{"flags": ["high_slippage" | "strategy_drift" | "post_trade_reversal" | "size_modified" | "low_confidence" | ...]}

Use only flags from this list. Empty list is fine."""

ALLOWED_FLAGS = frozenset(
    {
        "high_slippage",
        "strategy_drift",
        "post_trade_reversal",
        "size_modified",
        "low_confidence",
    }
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _build_user_prompt(
    *,
    event: dict[str, Any] | None,
    proposal: dict[str, Any] | None,
    verdict: dict[str, Any] | None,
    execution: dict[str, Any],
    positions_before: Any,
    positions_after: Any,
) -> str:
    return f"""EVENT: {json.dumps(event, indent=2, default=str)}
PROPOSAL: {json.dumps(proposal, indent=2, default=str)}
RISK VERDICT: {json.dumps(verdict, indent=2, default=str)}
EXECUTION: {json.dumps(execution, indent=2, default=str)}
POSITIONS BEFORE: {json.dumps(positions_before, indent=2, default=str)}
POSITIONS AFTER: {json.dumps(positions_after, indent=2, default=str)}

Explain."""


def _filter_flags(flags: list[str]) -> list[str]:
    return [f for f in flags if f in ALLOWED_FLAGS]


async def _fetch_positions(config: "Settings") -> list[dict[str, Any]]:
    if not config.injective_wallet_address:
        return []
    mcp = await get_mcp_client(config)
    if mcp is None or not mcp.is_healthy():
        return []
    try:
        raw = await mcp.call(
            "account_positions",
            {"address": config.injective_wallet_address},
        )
        if isinstance(raw, list):
            return [p for p in raw if isinstance(p, dict)]
    except Exception as exc:
        logger.warning("Auditor account_positions failed: %s", exc)
    return []


async def _process_execution(
    *,
    bus: "EventBus",
    store: "SentinelStore",
    config: "Settings",
    execution_msg: dict[str, Any],
) -> None:
    execution_id = str(execution_msg.get("id", ""))
    proposal_id = str(execution_msg.get("proposal_id", ""))
    if not execution_id:
        logger.warning("Auditor skipping execution without id")
        return

    execution = await store.get_execution(execution_id) or execution_msg
    proposal = await store.get_proposal(proposal_id) if proposal_id else None
    event = None
    if proposal and proposal.get("event_id"):
        event = await store.get_event(str(proposal["event_id"]))
    verdict = await store.get_verdict(proposal_id) if proposal_id else None

    positions_after = await _fetch_positions(config)
    positions_before: Any = []
    if execution.get("tool_result") and isinstance(execution["tool_result"], dict):
        before = execution["tool_result"].get("positionsBefore")
        if before is not None:
            positions_before = before
    if not positions_before:
        positions_before = {
            "note": "Pre-execution positions not snapshotted; state inferred from proposal/execution only.",
            "positions": [],
        }

    user_prompt = _build_user_prompt(
        event=event,
        proposal=proposal,
        verdict=verdict,
        execution=execution,
        positions_before=positions_before,
        positions_after=positions_after,
    )

    async def on_delta(accumulated: str) -> None:
        await bus.publish(
            TOPIC_AUDIT_STREAM,
            {
                "execution_id": execution_id,
                "proposal_id": proposal_id,
                "text": accumulated,
                "done": False,
            },
        )

    result = await anthropic_client.explain_execution(
        config,
        AUDIT_SYSTEM_PROMPT,
        user_prompt,
        on_text_delta=on_delta,
        temperature=0.5,
    )

    flags = _filter_flags(result.flags)
    if proposal and float(proposal.get("confidence", 1)) < 0.5:
        if "low_confidence" not in flags:
            flags.append("low_confidence")
    if verdict and verdict.get("modified_notional") is not None:
        if proposal and proposal.get("notional_usd") != verdict.get("modified_notional"):
            if "size_modified" not in flags:
                flags.append("size_modified")

    note = AuditNote(
        id=str(uuid.uuid4()),
        execution_id=execution_id,
        ts=_utc_now(),
        summary=result.summary,
        flags=flags,
    )
    await store.save_audit(note)
    await bus.publish(
        TOPIC_AUDIT_STREAM,
        {
            "execution_id": execution_id,
            "proposal_id": proposal_id,
            "text": result.summary,
            "done": True,
            "flags": flags,
        },
    )
    await bus.publish(
        TOPIC_AUDIT,
        {**note.model_dump(mode="json"), "proposal_id": proposal_id},
    )
    logger.info(
        "AUDITOR complete execution_id=%s flags=%s summary_preview=%s",
        execution_id,
        flags,
        result.summary[:100],
    )


async def run(
    *,
    bus: "EventBus",
    store: "SentinelStore",
    config: "Settings",
) -> None:
    await bus.publish("agent.status", {"agent": AGENT_NAME, "status": "running"})
    logger.info("Auditor started")
    try:
        async for msg in bus.subscribe(TOPIC_EXECUTION):
            try:
                await _process_execution(
                    bus=bus,
                    store=store,
                    config=config,
                    execution_msg=msg,
                )
            except Exception as exc:
                log_agent_loop_error(AGENT_NAME, exc, context="execution")
    except asyncio.CancelledError:
        await bus.publish("agent.status", {"agent": AGENT_NAME, "status": "stopped"})
        logger.info("Auditor stopped")
        raise
