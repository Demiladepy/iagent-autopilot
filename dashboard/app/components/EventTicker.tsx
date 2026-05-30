"use client";

import { DataList, FeedScrollArea, PanelCard } from "@/components/sentinel";
import { useSentinelStore } from "@/lib/sentinel-store";

export function EventTicker() {
  const ticker = useSentinelStore((s) => s.ticker);

  const items = ticker.map((ev) => ({
    id: ev.id,
    primary: (
      <>
        <span className="text-emerald-500">{ev.kind}</span>
        <span className="text-slate-500"> · {ev.market}</span>
      </>
    ),
    secondary:
      (ev.payload?.description as string) || JSON.stringify(ev.payload).slice(0, 80),
  }));

  return (
    <PanelCard
      title="03 · Event ticker"
      className="flex min-h-0 flex-1 flex-col"
      contentClassName="flex min-h-0 flex-1 flex-col"
    >
      <p className="mb-3 text-[10px] text-muted-foreground">Last 20 raw events (live)</p>
      <FeedScrollArea className="min-h-[200px] flex-1">
        <DataList items={items} empty="Waiting for events…" />
      </FeedScrollArea>
    </PanelCard>
  );
}
