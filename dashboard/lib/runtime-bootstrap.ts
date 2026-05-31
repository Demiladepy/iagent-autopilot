import { apiFetch } from "@/lib/api";
import type {
  AuditNote,
  DecisionChain,
  HealthResponse,
  MarketEvent,
  PortfolioSnapshot,
} from "@/lib/types";

export type ApiChain = {
  proposal_id: string;
  event?: DecisionChain["event"];
  proposal?: DecisionChain["proposal"];
  verdict?: DecisionChain["verdict"];
  execution?: DecisionChain["execution"];
  audit?: DecisionChain["audit"];
};

export type StateResponse = {
  positions: Record<string, unknown>[];
  balances: PortfolioSnapshot["balances"];
  today_pnl: number;
  kill_switch: boolean;
  last_audit: AuditNote | null;
  agents?: Record<string, string>;
  simulator_mode?: boolean;
  mcp_connected?: boolean;
  network?: string;
};

export type BootstrapActions = {
  setNetwork: (n: string) => void;
  setRuntime: (r: {
    ok: boolean;
    simulator_mode?: boolean;
    mcp_connected?: boolean;
  }) => void;
  setPortfolio: (p: Partial<PortfolioSnapshot>) => void;
  syncAgentsFromHealth: (statuses: Record<string, string>) => void;
  hydrateChains: (chains: DecisionChain[]) => void;
  hydrateEvents: (events: MarketEvent[]) => void;
  markDemoActivity: () => void;
};

/** Fetch status + hydrate dashboard state. Throws if the runtime is unreachable. */
export async function bootstrapRuntime(actions: BootstrapActions): Promise<void> {
  const status = await apiFetch<HealthResponse>("status");
  if (status.network) actions.setNetwork(status.network);
  actions.setRuntime({
    ok: status.ok,
    simulator_mode: status.simulator_mode ?? true,
    mcp_connected: status.mcp_connected ?? false,
  });
  actions.syncAgentsFromHealth(status.agents ?? {});
  actions.setPortfolio({ kill_switch: status.kill_switch ?? false });

  const [chains, state, events] = await Promise.all([
    apiFetch<ApiChain[]>("decisions?limit=50"),
    apiFetch<StateResponse>("state"),
    apiFetch<MarketEvent[]>("events?limit=20"),
  ]);

  const hydrated = chains
    .filter((c) => c.proposal)
    .map((c) => ({
      proposalId: c.proposal_id,
      sortTs: c.proposal!.ts,
      event: c.event,
      proposal: c.proposal!,
      verdict: c.verdict,
      execution: c.execution,
      audit: c.audit,
    }));

  actions.hydrateChains(hydrated);
  if (hydrated.length > 0) actions.markDemoActivity();

  actions.hydrateEvents(events);
  actions.setPortfolio({
    positions: state.positions ?? [],
    balances: state.balances ?? { bank: [], subaccount: [] },
    today_pnl: Number(state.today_pnl ?? 0),
    kill_switch: Boolean(state.kill_switch),
    last_audit: state.last_audit,
  });
  if (state.network) actions.setNetwork(state.network);
  if (state.agents) actions.syncAgentsFromHealth(state.agents);
  actions.setRuntime({
    ok: true,
    simulator_mode: state.simulator_mode ?? true,
    mcp_connected: state.mcp_connected ?? false,
  });
}
