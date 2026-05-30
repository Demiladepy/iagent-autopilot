import { create } from "zustand";
import type {
  AgentActivity,
  AgentName,
  AuditNote,
  AuditStreamState,
  DecisionChain,
  Execution,
  MarketEvent,
  PortfolioSnapshot,
  Proposal,
  RiskVerdict,
  RuntimeMeta,
  WsMessage,
} from "./types";

const AGENTS: AgentName[] = ["watcher", "analyst", "risk", "executor", "auditor"];

function defaultAgents(): Record<AgentName, AgentActivity> {
  return Object.fromEntries(
    AGENTS.map((a) => [a, { status: "idle", lastTs: null, lastSummary: "Waiting…" }])
  ) as Record<AgentName, AgentActivity>;
}

const defaultPortfolio = (): PortfolioSnapshot => ({
  positions: [],
  balances: { bank: [], subaccount: [] },
  today_pnl: 0,
  kill_switch: false,
  last_audit: null,
  updatedAt: new Date().toISOString(),
});

function eventDescription(ev: MarketEvent): string {
  const desc = ev.payload?.description;
  if (typeof desc === "string" && desc.trim()) return desc;
  return `${ev.kind.replace(/_/g, " ")} · ${ev.market}`;
}

function stripTopic<T extends Record<string, unknown>>(msg: WsMessage): T {
  const { topic: _t, ...rest } = msg;
  return rest as T;
}

export function buildDecisionChains(
  events: Record<string, MarketEvent>,
  proposals: Record<string, Proposal>,
  verdicts: Record<string, RiskVerdict>,
  executions: Record<string, Execution>,
  audits: Record<string, AuditNote>
): DecisionChain[] {
  return Object.values(proposals)
    .map((proposal) => {
      const execution = executions[proposal.id];
      return {
        proposalId: proposal.id,
        sortTs: proposal.ts,
        event: events[proposal.event_id],
        proposal,
        verdict: verdicts[proposal.id],
        execution,
        audit: execution ? audits[execution.id] : undefined,
      };
    })
    .sort((a, b) => new Date(b.sortTs).getTime() - new Date(a.sortTs).getTime());
}

type SentinelState = {
  connected: boolean;
  network: string;
  runtime: RuntimeMeta;
  portfolio: PortfolioSnapshot;
  events: Record<string, MarketEvent>;
  proposals: Record<string, Proposal>;
  verdicts: Record<string, RiskVerdict>;
  executions: Record<string, Execution>;
  audits: Record<string, AuditNote>;
  ticker: MarketEvent[];
  agents: Record<AgentName, AgentActivity>;
  recentProposalIds: string[];
  auditStream: AuditStreamState | null;
  setConnected: (v: boolean) => void;
  setNetwork: (n: string) => void;
  setRuntime: (r: Partial<RuntimeMeta>) => void;
  setKillSwitch: (v: boolean) => void;
  setPortfolio: (p: Partial<PortfolioSnapshot>) => void;
  hydrateChains: (chains: DecisionChain[]) => void;
  hydrateEvents: (events: MarketEvent[]) => void;
  syncAgentsFromHealth: (statuses: Record<string, string>) => void;
  handleMessage: (msg: WsMessage) => void;
  getDecisionChains: () => DecisionChain[];
};

export const useSentinelStore = create<SentinelState>((set, get) => ({
  connected: false,
  network: "testnet",
  runtime: { ok: false, simulator_mode: true, mcp_connected: false },
  portfolio: defaultPortfolio(),
  events: {},
  proposals: {},
  verdicts: {},
  executions: {},
  audits: {},
  ticker: [],
  agents: defaultAgents(),
  recentProposalIds: [],
  auditStream: null,

  setConnected: (v) => set({ connected: v }),
  setNetwork: (n) => set({ network: n }),
  setRuntime: (r) => set((s) => ({ runtime: { ...s.runtime, ...r } })),
  setKillSwitch: (v) =>
    set((s) => ({ portfolio: { ...s.portfolio, kill_switch: v, updatedAt: new Date().toISOString() } })),
  setPortfolio: (p) =>
    set((s) => ({ portfolio: { ...s.portfolio, ...p, updatedAt: new Date().toISOString() } })),

  syncAgentsFromHealth: (statuses) => {
    const agents = { ...get().agents };
    for (const name of AGENTS) {
      if (statuses[name]) {
        agents[name] = { ...agents[name], status: statuses[name] };
      }
    }
    set({ agents });
  },

  hydrateEvents: (events) => {
    const map = { ...get().events };
    for (const ev of events) map[ev.id] = ev;
    set({
      events: map,
      ticker: events.slice(0, 20),
    });
  },

  hydrateChains: (chains) => {
    const events = { ...get().events };
    const proposals = { ...get().proposals };
    const verdicts = { ...get().verdicts };
    const executions = { ...get().executions };
    const audits = { ...get().audits };
    const recentProposalIds: string[] = [];

    for (const c of chains) {
      if (c.event) events[c.event.id] = c.event;
      proposals[c.proposal.id] = c.proposal;
      recentProposalIds.push(c.proposal.id);
      if (c.verdict) verdicts[c.proposal.id] = c.verdict;
      if (c.execution) {
        executions[c.proposal.id] = c.execution;
        if (c.audit) audits[c.execution.id] = c.audit;
      }
    }
    set({ events, proposals, verdicts, executions, audits, recentProposalIds });
  },

  handleMessage: (msg) => {
    const topic = msg.topic;

    if (topic === "ping") return;

    if (topic === "connected") {
      get().syncAgentsFromHealth((msg.agents as Record<string, string>) ?? {});
      return;
    }

    if (topic === "kill") {
      get().setKillSwitch(Boolean(msg.enabled));
      return;
    }

    if (topic === "state_update") {
      const positions = (msg.positions as Record<string, unknown>[]) ?? [];
      const balances = (msg.balances as PortfolioSnapshot["balances"]) ?? {
        bank: [],
        subaccount: [],
      };
      set((s) => ({
        portfolio: {
          ...s.portfolio,
          positions,
          balances,
          today_pnl: Number(msg.today_pnl ?? s.portfolio.today_pnl),
          kill_switch: Boolean(msg.kill_switch ?? s.portfolio.kill_switch),
          last_audit: (msg.last_audit as AuditNote | null) ?? s.portfolio.last_audit,
          updatedAt: String(msg.ts ?? new Date().toISOString()),
        },
      }));
      if (msg.agents) get().syncAgentsFromHealth(msg.agents as Record<string, string>);
      return;
    }

    if (topic === "audit_stream") {
      const stream: AuditStreamState = {
        execution_id: String(msg.execution_id ?? ""),
        proposal_id: msg.proposal_id as string | undefined,
        text: String(msg.text ?? ""),
        done: Boolean(msg.done),
        flags: msg.flags as string[] | undefined,
      };
      set((s) => {
        const agents = { ...s.agents };
        agents.auditor = {
          status: stream.done ? "running" : "running",
          lastTs: new Date().toISOString(),
          lastSummary: stream.done
            ? "Audit complete"
            : "Streaming audit…",
        };
        return { auditStream: stream, agents };
      });
      return;
    }

    if (topic === "agent.status") {
      const agent = msg.agent as AgentName;
      const status = String(msg.status ?? "idle");
      if (AGENTS.includes(agent)) {
        set((s) => ({
          agents: {
            ...s.agents,
            [agent]: {
              ...s.agents[agent],
              status,
              lastTs: String(msg.ts ?? new Date().toISOString()),
            },
          },
        }));
      }
      return;
    }

    if (topic === "event") {
      const ev = stripTopic<MarketEvent>(msg);
      set((s) => {
        const agents = { ...s.agents };
        agents.watcher = {
          status: agents.watcher.status === "stopped" ? agents.watcher.status : "running",
          lastTs: ev.ts,
          lastSummary: eventDescription(ev),
        };
        const ticker = [ev, ...s.ticker.filter((e) => e.id !== ev.id)].slice(0, 20);
        return {
          events: { ...s.events, [ev.id]: ev },
          ticker,
          agents,
        };
      });
      return;
    }

    if (topic === "proposal") {
      const p = stripTopic<Proposal>(msg);
      set((s) => {
        const agents = { ...s.agents };
        agents.analyst = {
          status: "running",
          lastTs: p.ts,
          lastSummary: `${p.action} ${p.market ?? ""} · ${Math.round(p.confidence * 100)}% conf`,
        };
        const recentProposalIds = [p.id, ...s.recentProposalIds.filter((id) => id !== p.id)].slice(
          0,
          80
        );
        return {
          proposals: { ...s.proposals, [p.id]: p },
          recentProposalIds,
          agents,
        };
      });
      return;
    }

    if (topic === "verdict") {
      const v = stripTopic<RiskVerdict>(msg);
      set((s) => {
        const agents = { ...s.agents };
        agents.risk = {
          status: "running",
          lastTs: v.ts,
          lastSummary: v.approved
            ? `Approved${v.modified_notional != null ? ` · $${v.modified_notional}` : ""}`
            : `Rejected · ${v.reasons[0] ?? "policy"}`,
        };
        return {
          verdicts: { ...s.verdicts, [v.proposal_id]: v },
          agents,
        };
      });
      return;
    }

    if (topic === "execution") {
      const e = stripTopic<Execution>(msg);
      set((s) => {
        const agents = { ...s.agents };
        agents.executor = {
          status: "running",
          lastTs: e.ts,
          lastSummary:
            e.status === "success" && e.tx_hash
              ? `Tx ${e.tx_hash.slice(0, 10)}…`
              : `${e.status}${e.error ? ` · ${e.error}` : ""}`,
        };
        return {
          executions: { ...s.executions, [e.proposal_id]: e },
          agents,
        };
      });
      return;
    }

    if (topic === "audit") {
      const raw = stripTopic<AuditNote & { proposal_id?: string }>(msg);
      const a: AuditNote = {
        id: raw.id,
        execution_id: raw.execution_id,
        ts: raw.ts,
        summary: raw.summary,
        flags: raw.flags ?? [],
      };
      set((s) => {
        const agents = { ...s.agents };
        agents.auditor = {
          status: "running",
          lastTs: a.ts,
          lastSummary: a.summary.slice(0, 72) + (a.summary.length > 72 ? "…" : ""),
        };
        return {
          audits: { ...s.audits, [a.execution_id]: a },
          portfolio: { ...s.portfolio, last_audit: a },
          auditStream: null,
          agents,
        };
      });
    }
  },

  getDecisionChains: () => {
    const s = get();
    const chains = buildDecisionChains(s.events, s.proposals, s.verdicts, s.executions, s.audits);
    const order = s.recentProposalIds;
    if (order.length === 0) return chains;
    const rank = new Map(order.map((id, i) => [id, i]));
    return [...chains].sort((a, b) => {
      const ra = rank.get(a.proposalId) ?? 9999;
      const rb = rank.get(b.proposalId) ?? 9999;
      if (ra !== rb) return ra - rb;
      return new Date(b.sortTs).getTime() - new Date(a.sortTs).getTime();
    });
  },
}));
