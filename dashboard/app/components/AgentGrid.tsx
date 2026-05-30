"use client";

import { Brain, FileSearch, Radio, Shield, Zap } from "lucide-react";
import { AgentStatusIndicator, SectionLabel } from "@/components/sentinel";
import { useSentinelStore } from "@/lib/sentinel-store";
import type { AgentName } from "@/lib/types";
import { cn } from "@/lib/utils";

const AGENT_META: Record<
  AgentName,
  { label: string; role: string; icon: React.ElementType; num: string }
> = {
  watcher: { label: "Watcher", role: "Market surveillance", icon: Radio, num: "01" },
  analyst: { label: "Analyst", role: "Claude proposals", icon: Brain, num: "02" },
  risk: { label: "Risk", role: "Policy gate", icon: Shield, num: "03" },
  executor: { label: "Executor", role: "MCP execution", icon: Zap, num: "04" },
  auditor: { label: "Auditor", role: "Post-trade audit", icon: FileSearch, num: "05" },
};

const ORDER: AgentName[] = ["watcher", "analyst", "risk", "executor", "auditor"];

export function AgentGrid() {
  const wsAgents = useSentinelStore((s) => s.agents);

  return (
    <section>
      <SectionLabel index="01" className="mb-4">
        Agent fleet
      </SectionLabel>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {ORDER.map((name) => {
          const meta = AGENT_META[name];
          const Icon = meta.icon;
          const live = wsAgents[name];
          const status = live?.status ?? "idle";
          const lastTs = live?.lastTs;
          const summary = live?.lastSummary ?? "—";
          const running = status === "running";

          return (
            <div
              key={name}
              className={cn(
                "workbench-card rounded-2xl p-4 transition-all",
                running && "border-emerald-500/25"
              )}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[10px] text-neutral-600">{meta.num}</span>
                  <Icon className="h-4 w-4 text-emerald-400" />
                  <span className="text-sm font-semibold text-white">{meta.label}</span>
                </div>
                <AgentStatusIndicator status={status} />
              </div>
              <p className="mt-1 text-[10px] uppercase tracking-wider text-neutral-500">{meta.role}</p>
              <p className="mt-3 text-xs leading-snug text-neutral-300 line-clamp-2">{summary}</p>
              <p className="mt-2 font-mono text-[10px] text-neutral-600">
                {lastTs
                  ? new Date(lastTs).toLocaleTimeString()
                  : running
                    ? "active"
                    : "—"}
              </p>
            </div>
          );
        })}
      </div>
    </section>
  );
}
