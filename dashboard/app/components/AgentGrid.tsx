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
    <section className="workbench-agent-fleet">
      <SectionLabel index="01" className="workbench-section-label--secondary mb-5">
        Agent fleet
      </SectionLabel>
      <div className="workbench-agent-fleet-grid grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5">
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
                "workbench-card workbench-agent-card rounded-2xl transition-all",
                running && "workbench-agent-card--active"
              )}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="workbench-agent-num font-mono text-[10px]">{meta.num}</span>
                  <Icon className="workbench-agent-icon h-4 w-4 shrink-0" />
                  <span className="workbench-agent-label text-sm font-semibold">{meta.label}</span>
                </div>
                <AgentStatusIndicator
                  status={status}
                  className={running ? undefined : "!bg-neutral-600 shadow-none"}
                />
              </div>
              <p className="workbench-agent-role mt-1.5 text-[10px] uppercase tracking-wider">
                {meta.role}
              </p>
              <p className="workbench-agent-summary mt-3 text-xs leading-snug line-clamp-2">
                {summary}
              </p>
              <p className="workbench-agent-meta mt-2.5 font-mono text-[10px]">
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
