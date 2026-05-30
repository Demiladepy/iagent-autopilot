"""Pydantic v2 domain models for iAgent Autopilot."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class MarketEvent(BaseModel):
    id: str  # uuid
    ts: datetime
    kind: Literal[
        "funding_flip",
        "drawdown",
        "breakout",
        "liquidation_cluster",
        "position_drift",
        "manual",
        "synthetic",
    ]
    market: str  # "BTC", "ETH", "INJ"
    payload: dict  # event-specific data
    source: Literal["watcher", "simulator", "manual"]


class ProposalOutput(BaseModel):
    """Claude JSON output — validated before wrapping in Proposal."""

    action: Literal["open", "close", "adjust", "none"]
    market: str | None = None
    side: Literal["long", "short"] | None = None
    notional_usd: float | None = None
    leverage: float | None = None
    reasoning: str
    confidence: float = Field(ge=0.0, le=1.0)
    expected_hold_hours: float | None = None
    invalidation: str | None = None

    @model_validator(mode="after")
    def _require_invalidation_for_action(self) -> ProposalOutput:
        if self.action != "none":
            if not self.invalidation or not str(self.invalidation).strip():
                raise ValueError("invalidation is required when action is not 'none'")
        return self


class Proposal(BaseModel):
    id: str
    event_id: str
    ts: datetime
    action: Literal["open", "close", "adjust", "none"]
    market: str | None
    side: Literal["long", "short"] | None
    notional_usd: float | None
    leverage: float | None
    reasoning: str
    confidence: float  # 0.0-1.0
    expected_hold_hours: float | None
    invalidation: str | None


class RiskVerdict(BaseModel):
    proposal_id: str
    ts: datetime
    approved: bool
    reasons: list[str]
    modified_notional: float | None  # risk may shrink size
    modified_leverage: float | None


class Execution(BaseModel):
    id: str
    proposal_id: str
    ts: datetime
    status: Literal["success", "failed", "skipped"]
    tx_hash: str | None
    tool_called: str | None
    tool_args: dict | None
    tool_result: dict | None
    error: str | None


class AuditNote(BaseModel):
    id: str
    execution_id: str
    ts: datetime
    summary: str
    flags: list[str]  # e.g. ["high_slippage", "strategy_drift", "post_trade_reversal"]


class StrategyConfig(BaseModel):
    """Runtime strategy limits (single-row store)."""

    id: int = 1
    text: str = ""
    max_notional_usd: float = Field(default=1000.0, ge=0)
    max_leverage: float = Field(default=10.0, ge=1)
    max_daily_loss_usd: float = Field(default=500.0, ge=0)
    allowed_markets: list[str] = Field(default_factory=lambda: ["BTC", "ETH", "INJ"])
    updated_at: datetime | None = None
