"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import { Link2, Play, Plus } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { PanelCard } from "@/components/sentinel";
import { useSentinelStore } from "@/lib/sentinel-store";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

const SCENARIOS = [
  { id: "funding_reversion", label: "Funding Reversion" },
  { id: "risk_block", label: "Risk Block" },
  { id: "kill_switch", label: "Kill Switch" },
] as const;

export function DemoControls() {
  const simulatorMode = useSentinelStore((s) => s.runtime.simulator_mode);
  const setRuntime = useSentinelStore((s) => s.setRuntime);
  const { data: status } = useSWR<{ simulator_mode?: boolean }>("/api/proxy/status", fetcher, {
    refreshInterval: 10000,
  });

  useEffect(() => {
    if (status?.simulator_mode != null) {
      setRuntime({ simulator_mode: status.simulator_mode });
    }
  }, [status, setRuntime]);

  const simOn = simulatorMode ?? status?.simulator_mode ?? true;

  const [loading, setLoading] = useState<string | null>(null);
  const [injectOpen, setInjectOpen] = useState(false);
  const [market, setMarket] = useState("BTC");
  const [kind, setKind] = useState("synthetic");
  const [payloadJson, setPayloadJson] = useState('{"note":"manual demo event"}');

  async function runScenario(id: string) {
    if (!simOn) {
      toast.error("SIMULATOR_MODE is disabled on the runtime");
      return;
    }
    setLoading(id);
    try {
      const res = await fetch(`/api/proxy/sim/run/${id}`, { method: "POST" });
      if (!res.ok) throw new Error(await res.text());
      toast.success(`Scenario started: ${id}`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Scenario failed");
    } finally {
      setLoading(null);
    }
  }

  async function injectEvent() {
    if (!simOn) {
      toast.error("SIMULATOR_MODE is disabled on the runtime");
      return;
    }
    let payload: Record<string, unknown> = {};
    try {
      payload = JSON.parse(payloadJson) as Record<string, unknown>;
    } catch {
      toast.error("Payload must be valid JSON");
      return;
    }
    setLoading("inject");
    try {
      const res = await fetch("/api/proxy/sim/event", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          id: crypto.randomUUID(),
          ts: new Date().toISOString(),
          kind,
          market,
          payload,
          source: "manual",
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      toast.success("Event injected");
      setInjectOpen(false);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Inject failed");
    } finally {
      setLoading(null);
    }
  }

  async function runRealOnChainDemo() {
    setLoading("real_onchain");
    try {
      const res = await fetch("/api/proxy/demo/force-open", { method: "POST" });
      if (!res.ok) throw new Error(await res.text());
      const body = (await res.json()) as { proposal_id?: string };
      toast.success(
        body?.proposal_id
          ? `Real demo triggered (proposal ${body.proposal_id.slice(0, 8)}…)`
          : "Real demo triggered",
      );
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Demo trigger failed");
    } finally {
      setLoading(null);
    }
  }

  return (
    <PanelCard title="Co-pilot · Demo scenarios" contentClassName="space-y-3">
      {!simOn && (
        <p className="mb-3 rounded-md border border-amber-500/30 bg-amber-950/30 px-2 py-1.5 text-xs text-amber-200">
          Simulator off — set SIMULATOR_MODE=true in runtime/.env
        </p>
      )}
      <div className="space-y-2">
        {SCENARIOS.map((s) => (
          <Button
            key={s.id}
            variant="outline"
            className="h-10 w-full justify-start gap-2 border-white/10 hover:border-emerald-500/40 hover:bg-emerald-500/10"
            onClick={() => runScenario(s.id)}
            disabled={loading !== null || !simOn}
          >
            <Play className="h-3.5 w-3.5 text-emerald-500" />
            Run: {s.label}
            {loading === s.id && <span className="ml-auto text-xs opacity-60">…</span>}
          </Button>
        ))}
        <Button
          className="h-10 w-full justify-start gap-2 bg-emerald-500/15 text-emerald-200 ring-1 ring-emerald-500/25 hover:bg-emerald-500/25"
          onClick={runRealOnChainDemo}
          disabled={loading !== null}
        >
          <Link2 className="h-3.5 w-3.5 text-emerald-300" />
          Run: Real On-Chain Demo
          {loading === "real_onchain" && <span className="ml-auto text-xs opacity-60">…</span>}
        </Button>
        <Button
          variant="secondary"
          className="h-10 w-full justify-start gap-2"
          onClick={() => setInjectOpen(true)}
          disabled={!simOn}
        >
          <Plus className="h-3.5 w-3.5" />
          Inject custom event…
        </Button>
      </div>

      <Dialog open={injectOpen} onOpenChange={setInjectOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Inject market event</DialogTitle>
            <DialogDescription>
              Published to the event bus as a manual simulator event.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <label className="text-xs text-muted-foreground">Market</label>
              <Input
                value={market}
                onChange={(e) => setMarket(e.target.value.toUpperCase())}
                className="mt-1"
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Kind</label>
              <Input value={kind} onChange={(e) => setKind(e.target.value)} className="mt-1" />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Payload (JSON)</label>
              <Textarea
                value={payloadJson}
                onChange={(e) => setPayloadJson(e.target.value)}
                className="mt-1 font-mono text-xs"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setInjectOpen(false)}>
              Cancel
            </Button>
            <Button onClick={injectEvent} disabled={loading === "inject"}>
              Inject
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PanelCard>
  );
}
