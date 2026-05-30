"use client";

import { useEffect, useState } from "react";
import { Brain, Check, Loader2, Shield, Zap } from "lucide-react";
import { INTEGRATIONS } from "@/lib/brand-content";
import { cn } from "@/lib/utils";

const STEPS = [
  { id: "analyze", label: "Analyzing market event…", icon: Loader2, spin: true },
  { id: "proposal", label: "Analyst proposed long BTC · $50 notional", icon: Brain },
  { id: "risk", label: "Risk approved — within policy limits", icon: Shield },
  { id: "exec", label: "Executor submitted (dry-run receipt)", icon: Zap },
  { id: "done", label: "Auditor summary ready", icon: Check },
] as const;

export function WorkflowMockup() {
  const [step, setStep] = useState(0);

  useEffect(() => {
    const t = setInterval(() => setStep((s) => (s + 1) % STEPS.length), 2800);
    return () => clearInterval(t);
  }, []);

  const current = STEPS[step];
  const Icon = current.icon;

  return (
    <div className="workbench-mockup mx-auto w-full max-w-xl overflow-hidden">
      <div className="border-b border-white/10 px-4 py-3 md:px-5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-md bg-emerald-500/15 px-2 py-0.5 font-mono text-[10px] text-emerald-400">
            funding_flip · BTC
          </span>
          <span className="text-[10px] text-neutral-500">· Injective perps</span>
        </div>
        <p className="mt-2 text-sm text-neutral-300">
          Read strategy policy and propose a funding reversion entry within max notional and leverage.
        </p>
      </div>

      <div className="flex flex-wrap gap-1.5 border-b border-white/10 px-4 py-2 md:px-5">
        {INTEGRATIONS.slice(0, 5).map((name) => (
          <span key={name} className="integration-pill text-[10px]">
            {name}
          </span>
        ))}
        <span className="integration-pill text-[10px] text-neutral-600">+ more</span>
      </div>

      <div className="flex border-b border-white/10 text-[10px] uppercase tracking-[0.15em]">
        {(["Actions", "Pipeline", "Skills"] as const).map((tab, i) => (
          <button
            key={tab}
            type="button"
            className={cn(
              "flex-1 px-4 py-2.5 transition-colors",
              i === 1 ? "border-b-2 border-emerald-500/80 text-white" : "text-neutral-500"
            )}
          >
            {tab}
          </button>
        ))}
      </div>

      <div className="space-y-3 px-4 py-5 md:px-5">
        <div className="rounded-lg border border-white/8 bg-white/[0.02] p-3">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-neutral-500">Skill</p>
          <p className="mt-1 text-sm leading-relaxed text-neutral-200">
            Funding rate crossed threshold — evaluate mean-reversion per strategy text and risk limits.
          </p>
        </div>

        <div className="flex items-center gap-2 rounded-lg border border-emerald-500/20 bg-emerald-500/5 px-3 py-2.5">
          <Icon
            className={cn(
              "h-4 w-4 shrink-0 text-emerald-400",
              "spin" in current && current.spin && "animate-spin"
            )}
          />
          <span className="text-sm text-emerald-100/90">{current.label}</span>
        </div>

        <div className="flex gap-2">
          {STEPS.map((s, i) => (
            <div
              key={s.id}
              className={cn(
                "h-1 flex-1 rounded-full transition-colors duration-500",
                i <= step ? "bg-emerald-500/60" : "bg-white/10"
              )}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
