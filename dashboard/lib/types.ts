export type AgentName = "watcher" | "analyst" | "risk" | "executor" | "auditor";

export type MarketEvent = {
  id: string;
  ts: string;
  kind: string;
  market: string;
  payload: Record<string, unknown>;
  source: string;
};

export type Proposal = {
  id: string;
  event_id: string;
  ts: string;
  action: string;
  market: string | null;
  side: string | null;
  notional_usd: number | null;
  leverage: number | null;
  reasoning: string;
  confidence: number;
  expected_hold_hours?: number | null;
  invalidation?: string | null;
};

export type RiskVerdict = {
  proposal_id: string;
  ts: string;
  approved: boolean;
  reasons: string[];
  modified_notional: number | null;
  modified_leverage: number | null;
};

export type Execution = {
  id: string;
  proposal_id: string;
  ts: string;
  status: "success" | "failed" | "skipped";
  tx_hash: string | null;
  tool_called: string | null;
  tool_args: Record<string, unknown> | null;
  tool_result: Record<string, unknown> | null;
  error: string | null;
};

export type AuditNote = {
  id: string;
  execution_id: string;
  ts: string;
  summary: string;
  flags: string[];
};

export type DecisionChain = {
  proposalId: string;
  sortTs: string;
  event?: MarketEvent;
  proposal: Proposal;
  verdict?: RiskVerdict;
  execution?: Execution;
  audit?: AuditNote;
};

export type AgentActivity = {
  status: string;
  lastTs: string | null;
  lastSummary: string;
};

export type PortfolioSnapshot = {
  positions: Record<string, unknown>[];
  balances: {
    bank?: { denom?: string; amount?: string }[];
    subaccount?: { denom?: string; availableBalance?: string; totalBalance?: string }[];
  };
  today_pnl: number;
  kill_switch: boolean;
  last_audit: AuditNote | null;
  updatedAt: string;
};

export type RuntimeMeta = {
  simulator_mode: boolean;
  mcp_connected: boolean;
  ok: boolean;
};

export type AuditStreamState = {
  execution_id: string;
  proposal_id?: string;
  text: string;
  done: boolean;
  flags?: string[];
};

export type HealthResponse = {
  ok: boolean;
  agents: Record<string, string>;
  kill_switch: boolean;
  simulator_mode?: boolean;
  mcp_connected?: boolean;
  network?: string;
};

export type WsMessage = {
  topic: string;
  [key: string]: unknown;
};
