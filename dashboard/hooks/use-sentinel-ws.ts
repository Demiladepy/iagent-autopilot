"use client";

import { useEffect, useRef } from "react";
import { resolveWsUrl } from "@/lib/api";
import { bootstrapRuntime } from "@/lib/runtime-bootstrap";
import { useSentinelStore } from "@/lib/sentinel-store";
import type { WsMessage } from "@/lib/types";

const MAX_BACKOFF_MS = 30_000;
const WAKE_POLL_MS = 3_000;
const WAKE_FAIL_AFTER_MS = 60_000;

export function useSentinelWebSocket() {
  const handleMessage = useSentinelStore((s) => s.handleMessage);
  const setConnected = useSentinelStore((s) => s.setConnected);
  const setNetwork = useSentinelStore((s) => s.setNetwork);
  const setRuntime = useSentinelStore((s) => s.setRuntime);
  const setPortfolio = useSentinelStore((s) => s.setPortfolio);
  const hydrateChains = useSentinelStore((s) => s.hydrateChains);
  const hydrateEvents = useSentinelStore((s) => s.hydrateEvents);
  const syncAgentsFromHealth = useSentinelStore((s) => s.syncAgentsFromHealth);
  const markDemoActivity = useSentinelStore((s) => s.markDemoActivity);
  const setBootPhase = useSentinelStore((s) => s.setBootPhase);
  const bootstrapRetryNonce = useSentinelStore((s) => s.bootstrapRetryNonce);

  const attemptRef = useRef(0);
  const wsRef = useRef<WebSocket | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const wakeTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const wakeStartedRef = useRef<number>(Date.now());

  useEffect(() => {
    let cancelled = false;

    wakeStartedRef.current = Date.now();
    setBootPhase("waking");

    async function tryBootstrap(): Promise<boolean> {
      if (cancelled) return false;
      try {
        await bootstrapRuntime({
          setNetwork,
          setRuntime,
          setPortfolio,
          syncAgentsFromHealth,
          hydrateChains,
          hydrateEvents,
          markDemoActivity,
        });
        setBootPhase("ready");
        return true;
      } catch {
        setRuntime({ ok: false });
        const elapsed = Date.now() - wakeStartedRef.current;
        if (elapsed >= WAKE_FAIL_AFTER_MS) {
          setBootPhase("failed");
        } else {
          setBootPhase("waking");
        }
        return false;
      }
    }

    void tryBootstrap();

    wakeTimerRef.current = setInterval(() => {
      const phase = useSentinelStore.getState().bootPhase;
      if (phase === "ready" || phase === "failed") return;
      void tryBootstrap();
    }, WAKE_POLL_MS);

    async function connect() {
      if (cancelled) return;
      if (useSentinelStore.getState().bootPhase !== "ready") return;

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

    const unsub = useSentinelStore.subscribe((state, prev) => {
      if (state.bootPhase === "ready" && prev.bootPhase !== "ready") {
        void connect();
      }
    });

    if (useSentinelStore.getState().bootPhase === "ready") {
      void connect();
    }

    return () => {
      cancelled = true;
      unsub();
      if (timerRef.current) clearTimeout(timerRef.current);
      if (wakeTimerRef.current) clearInterval(wakeTimerRef.current);
      wsRef.current?.close();
      setConnected(false);
    };
  }, [
    bootstrapRetryNonce,
    handleMessage,
    hydrateChains,
    hydrateEvents,
    markDemoActivity,
    setBootPhase,
    setConnected,
    setNetwork,
    setPortfolio,
    setRuntime,
    syncAgentsFromHealth,
  ]);
}
