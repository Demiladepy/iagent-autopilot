"use client";

import { Wallet, TrendingUp, TrendingDown } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { DataList, PanelCard } from "@/components/sentinel";
import { useSentinelStore } from "@/lib/sentinel-store";

type Position = {
  symbol?: string;
  ticker?: string;
  side?: string;
  direction?: string;
  unrealizedPnl?: string;
  unrealized_pnl?: string;
};

export function PositionPanel() {
  const portfolio = useSentinelStore((s) => s.portfolio);
  const positions = (portfolio.positions ?? []) as Position[];
  const bank = portfolio.balances.bank ?? [];
  const sub = portfolio.balances.subaccount ?? [];
  const pnl = portfolio.today_pnl;
  const pnlUp = pnl >= 0;

  const positionItems = positions.map((p, i) => {
    const sym = p.symbol ?? p.ticker ?? "—";
    const side = p.side ?? p.direction ?? "";
    const upnl = p.unrealizedPnl ?? p.unrealized_pnl ?? "—";
    return {
      id: `${sym}-${i}`,
      primary: (
        <>
          <span className="font-medium">{sym}</span>
          <span className="ml-1 capitalize text-muted-foreground">{side}</span>
        </>
      ),
      trailing: <span className="text-muted-foreground">{upnl}</span>,
    };
  });

  const balanceItems = [
    ...bank.slice(0, 4).map((b, i) => ({
      id: `b-${i}`,
      primary: b.denom?.split("/").pop() ?? "bank",
      trailing: b.amount,
    })),
    ...sub.slice(0, 4).map((s, i) => ({
      id: `s-${i}`,
      primary: s.denom?.split("/").pop() ?? "sub",
      trailing: s.availableBalance ?? s.totalBalance,
    })),
  ];

  return (
    <PanelCard
      title={
        <span className="flex items-center gap-2">
          <Wallet className="h-4 w-4 text-emerald-500" />
          Portfolio
        </span>
      }
      contentClassName="space-y-4"
    >
      <div className="flex items-center justify-between rounded-lg bg-slate-950/60 px-3 py-2">
        <span className="text-xs text-muted-foreground">Today PnL</span>
        <span
          className={`flex items-center gap-1 font-mono text-lg font-semibold ${pnlUp ? "text-emerald-400" : "text-red-400"}`}
        >
          {pnlUp ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
          {pnlUp ? "+" : ""}${pnl.toFixed(2)}
        </span>
      </div>

      <div>
        <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          Positions
        </p>
        <DataList items={positionItems} empty="No open positions" />
      </div>

      <Separator className="bg-slate-800" />

      <div>
        <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          Balances
        </p>
        <DataList
          items={balanceItems}
          empty="Connect MCP + wallet for balances"
          className="max-h-32 overflow-y-auto"
        />
      </div>

      <div className="flex justify-end">
        <Badge variant={portfolio.kill_switch ? "destructive" : "outline"}>
          Kill {portfolio.kill_switch ? "ON" : "OFF"}
        </Badge>
      </div>
    </PanelCard>
  );
}
