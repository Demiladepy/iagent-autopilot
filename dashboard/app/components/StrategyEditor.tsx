"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { PanelCard } from "@/components/sentinel";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

type Strategy = {
  text: string;
  max_notional_usd: number;
  max_leverage: number;
  max_daily_loss_usd: number;
  allowed_markets: string[];
  updated_at?: string;
};

type ParseProposed = {
  text: string;
  max_notional_usd: number;
  max_leverage: number;
  max_daily_loss_usd: number;
  allowed_markets: string[];
};

export function StrategyEditor() {
  const { data, mutate } = useSWR<Strategy>("/api/proxy/strategy", fetcher);
  const [text, setText] = useState("");
  const [maxNotional, setMaxNotional] = useState(50);
  const [maxLeverage, setMaxLeverage] = useState(2);
  const [maxDailyLoss, setMaxDailyLoss] = useState(25);
  const [markets, setMarkets] = useState<string[]>(["BTC", "ETH", "INJ"]);
  const [saving, setSaving] = useState(false);
  const [parsing, setParsing] = useState(false);
  const [preview, setPreview] = useState<ParseProposed | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);

  useEffect(() => {
    if (data) {
      setText(data.text ?? "");
      setMaxNotional(data.max_notional_usd ?? 50);
      setMaxLeverage(data.max_leverage ?? 2);
      setMaxDailyLoss(data.max_daily_loss_usd ?? 25);
      setMarkets(data.allowed_markets ?? ["BTC", "ETH", "INJ"]);
    }
  }, [data]);

  async function parseNl() {
    if (!text.trim()) return;
    setParsing(true);
    try {
      const res = await fetch("/api/proxy/strategy/parse", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (!res.ok) throw new Error(await res.text());
      const body = await res.json();
      setPreview(body.proposed as ParseProposed);
      setPreviewOpen(true);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Parse failed");
    } finally {
      setParsing(false);
    }
  }

  function applyPreview() {
    if (!preview) return;
    setText(preview.text);
    setMaxNotional(preview.max_notional_usd);
    setMaxLeverage(preview.max_leverage);
    setMaxDailyLoss(preview.max_daily_loss_usd);
    setMarkets(preview.allowed_markets);
    setPreviewOpen(false);
    toast.message("Preview applied — click Save to persist");
  }

  async function save() {
    setSaving(true);
    try {
      const res = await fetch("/api/proxy/strategy", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          text,
          max_notional_usd: maxNotional,
          max_leverage: maxLeverage,
          max_daily_loss_usd: maxDailyLoss,
          allowed_markets: markets,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      await mutate();
      toast.success("Strategy saved");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <PanelCard title="Skill studio · Strategy" contentClassName="space-y-3">
      <Textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Describe your strategy in plain English…"
        className="min-h-[120px] resize-none"
      />
      <div className="mt-3 flex flex-wrap gap-2">
        <LimitChip label="Notional" value={`$${maxNotional}`} />
        <LimitChip label="Leverage" value={`${maxLeverage}x`} />
        <LimitChip label="Daily loss" value={`$${maxDailyLoss}`} />
        {markets.map((m) => (
          <Badge key={m} variant="outline" className="border-emerald-500/40 text-emerald-400">
            {m}
          </Badge>
        ))}
      </div>
      <div className="mt-4 grid grid-cols-2 gap-2">
        <div>
          <label className="text-[10px] uppercase text-muted-foreground">Max notional $</label>
          <Input
            type="number"
            value={maxNotional}
            onChange={(e) => setMaxNotional(Number(e.target.value))}
            className="mt-1 h-9"
          />
        </div>
        <div>
          <label className="text-[10px] uppercase text-muted-foreground">Max leverage</label>
          <Input
            type="number"
            value={maxLeverage}
            onChange={(e) => setMaxLeverage(Number(e.target.value))}
            className="mt-1 h-9"
          />
        </div>
        <div className="col-span-2">
          <label className="text-[10px] uppercase text-muted-foreground">Max daily loss $</label>
          <Input
            type="number"
            value={maxDailyLoss}
            onChange={(e) => setMaxDailyLoss(Number(e.target.value))}
            className="mt-1 h-9"
          />
        </div>
      </div>
      <div className="mt-4 flex gap-2">
        <Button variant="outline" className="flex-1" onClick={parseNl} disabled={parsing}>
          {parsing ? "Parsing…" : "Parse"}
        </Button>
        <Button className="flex-1" onClick={save} disabled={saving}>
          {saving ? "Saving…" : "Save"}
        </Button>
      </div>
      {data?.updated_at && (
        <p className="mt-2 text-[10px] text-muted-foreground">
          Updated {new Date(data.updated_at).toLocaleString()}
        </p>
      )}

      <Dialog open={previewOpen} onOpenChange={setPreviewOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Confirm parsed limits</DialogTitle>
            <DialogDescription>
              Claude extracted these limits from your text. Apply to the editor, then Save.
            </DialogDescription>
          </DialogHeader>
          {preview && (
            <div className="space-y-3 text-sm">
              <p className="rounded-md bg-slate-950/60 p-3 text-slate-300">{preview.text}</p>
              <div className="flex flex-wrap gap-2">
                <LimitChip label="Notional" value={`$${preview.max_notional_usd}`} />
                <LimitChip label="Leverage" value={`${preview.max_leverage}x`} />
                <LimitChip label="Daily loss" value={`$${preview.max_daily_loss_usd}`} />
                {preview.allowed_markets.map((m) => (
                  <Badge key={m} variant="outline">
                    {m}
                  </Badge>
                ))}
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setPreviewOpen(false)}>
              Cancel
            </Button>
            <Button onClick={applyPreview}>Apply to editor</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PanelCard>
  );
}

function LimitChip({ label, value }: { label: string; value: string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-slate-700 bg-slate-950/50 px-2.5 py-0.5 text-xs">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium text-emerald-400">{value}</span>
    </span>
  );
}
