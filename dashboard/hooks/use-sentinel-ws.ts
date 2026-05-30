"use client";

import { useEffect, useRef } from "react";
import { apiFetch, resolveWsUrl } from "@/lib/api";
import { useSentinelStore } from "@/lib/sentinel-store";
import type {
  AuditNote,
  DecisionChain,
  HealthResponse,
  MarketEvent,
  PortfolioSnapshot,
  WsMessage,
} from "@/lib/types";

const MAX_BACKOFF_MS = 30_000;

type ApiChain = {
  proposal_id: string;
  event?: DecisionChain["event"];
  proposal?: DecisionChain["proposal"];
  verdict?: DecisionChain["verdict"];
  execution?: DecisionChain["execution"];
  audit?: DecisionChain["audit"];
};

type StateResponse = {
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

export function useSentinelWebSocket() {
  const handleMessage = useSentinelStore((s) => s.handleMessage);
  const setConnected = useSentinelStore((s) => s.setConnected);
  const setNetwork = useSentinelStore((s) => s.setNetwork);
  const setRuntime = useSentinelStore((s) => s.setRuntime);
  const setPortfolio = useSentinelStore((s) => s.setPortfolio);
  const hydrateChains = useSentinelStore((s) => s.hydrateChains);
  const hydrateEvents = useSentinelStore((s) => s.hydrateEvents);
  const syncAgentsFromHealth = useSentinelStore((s) => s.syncAgentsFromHealth);
  const attemptRef = useRef(0);
  const wsRef = useRef<WebSocket | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      try {
        const status = await apiFetch<HealthResponse>("status");
        if (status.network) setNetwork(status.network);
        setRuntime({
          ok: status.ok,
          simulator_mode: status.simulator_mode ?? true,
          mcp_connected: status.mcp_connected ?? false,
        });
        syncAgentsFromHealth(status.agents ?? {});
        setPortfolio({ kill_switch: status.kill_switch ?? false });

        const [chains, state, events] = await Promise.all([
          apiFetch<ApiChain[]>("decisions?limit=50"),
          apiFetch<StateResponse>("state"),
          apiFetch<MarketEvent[]>("events?limit=20"),
        ]);

        hydrateChains(
          chains
            .filter((c) => c.proposal)
            .map((c) => ({
              proposalId: c.proposal_id,
              sortTs: c.proposal!.ts,
              event: c.event,
              proposal: c.proposal!,
              verdict: c.verdict,
              execution: c.execution,
              audit: c.audit,
            }))
        );

        hydrateEvents(events);
        setPortfolio({
          positions: state.positions ?? [],
          balances: state.balances ?? { bank: [], subaccount: [] },
          today_pnl: Number(state.today_pnl ?? 0),
          kill_switch: Boolean(state.kill_switch),
          last_audit: state.last_audit,
        });
        if (state.network) setNetwork(state.network);
        if (state.agents) syncAgentsFromHealth(state.agents);
        setRuntime({
          ok: true,
          simulator_mode: state.simulator_mode ?? true,
          mcp_connected: state.mcp_connected ?? false,
        });
      } catch {
        setRuntime({ ok: false });
      }
    }

    void bootstrap();

    async function connect() {
      if (cancelled) return;
      const url = await resolveWsUrl();
      if (!url) return;

      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        attemptRef.current = 0;
        setConnected(true);
      };

      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data as string) as WsMessage;
          handleMessage(msg);
        } catch {
          /* ignore malformed */
        }
      };

      ws.onclose = () => {
        setConnected(false);
        wsRef.current = null;
        if (cancelled) return;
        const delay = Math.min(1000 * 2 ** attemptRef.current, MAX_BACKOFF_MS);
        attemptRef.current += 1;
        timerRef.current = setTimeout(() => void connect(), delay);
      };

      ws.onerror = () => ws.close();
    }

    void connect();

    return () => {
      cancelled = true;
      if (timerRef.current) clearTimeout(timerRef.current);
      wsRef.current?.close();
      setConnected(false);
    };
  }, [
    handleMessage,
    hydrateChains,
    hydrateEvents,
    setConnected,
    setNetwork,
    setPortfolio,
    setRuntime,
    syncAgentsFromHealth,
  ]);
}
