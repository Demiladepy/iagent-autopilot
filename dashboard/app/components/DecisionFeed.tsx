"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { DecisionDisclosure, FeedScrollArea, SectionLabel } from "@/components/sentinel";
import { buildDecisionChains, useSentinelStore } from "@/lib/sentinel-store";

export function DecisionFeed() {
  const bootPhase = useSentinelStore((s) => s.bootPhase);
  const hasDemoActivity = useSentinelStore((s) => s.hasDemoActivity);
  const events = useSentinelStore((s) => s.events);
  const proposals = useSentinelStore((s) => s.proposals);
  const verdicts = useSentinelStore((s) => s.verdicts);
  const executions = useSentinelStore((s) => s.executions);
  const audits = useSentinelStore((s) => s.audits);
  const recentIds = useSentinelStore((s) => s.recentProposalIds);

  const seenRef = useRef<Set<string>>(new Set());
  const [animateIds, setAnimateIds] = useState<Set<string>>(() => new Set());

  const chains = useMemo(() => {
    const all = buildDecisionChains(events, proposals, verdicts, executions, audits);
    const rank = new Map(recentIds.map((id, i) => [id, i]));
    return [...all]
      .sort((a, b) => {
        const ra = rank.get(a.proposalId) ?? 9999;
        const rb = rank.get(b.proposalId) ?? 9999;
        if (ra !== rb) return ra - rb;
        return new Date(b.sortTs).getTime() - new Date(a.sortTs).getTime();
      })
      .slice(0, 40);
  }, [events, proposals, verdicts, executions, audits, recentIds]);

  useEffect(() => {
    const fresh = new Set<string>();
    for (const c of chains) {
      if (!seenRef.current.has(c.proposalId)) {
        seenRef.current.add(c.proposalId);
        fresh.add(c.proposalId);
      }
    }
    if (fresh.size === 0) return;
    setAnimateIds(fresh);
    const t = setTimeout(() => setAnimateIds(new Set()), 500);
    return () => clearTimeout(t);
  }, [chains]);

  const showJudgeHint = bootPhase === "ready" && !hasDemoActivity && chains.length === 0;

  return (
    <section className="workbench-decision-section flex min-h-0 flex-1 flex-col">
      <div className="mb-5 flex items-end justify-between gap-4 px-1">
        <SectionLabel index="02" className="workbench-section-label--primary">
          Decision pipeline
        </SectionLabel>
        <span className="shrink-0 font-mono text-[10px] text-neutral-500">
          {chains.length} chains
        </span>
      </div>
      <FeedScrollArea className="workbench-decision-feed h-[calc(100vh-280px)] min-h-[400px] xl:min-h-[440px]">
        <div className="space-y-5 p-1 pb-10" role="feed" aria-label="Decision timeline">
          {chains.length === 0 && (
            <div className="workbench-card workbench-decision-empty rounded-2xl border-dashed text-center">
              {showJudgeHint ? (
                <p className="mx-auto max-w-md text-sm leading-relaxed text-emerald-200/85">
                  Click{" "}
                  <span className="font-medium text-emerald-300">Run: Funding Reversion</span> to
                  watch five AI agents propose, risk-check, execute, and audit a trade — live.
                </p>
              ) : (
                <p className="text-sm text-muted-foreground">
                  No decisions yet. Run a demo scenario to watch the pipeline live.
                </p>
              )}
            </div>
          )}
          {chains.map((chain, i) => (
            <DecisionDisclosure
              key={chain.proposalId}
              chain={chain}
              animate={animateIds.has(chain.proposalId)}
              defaultOpen={i === 0}
            />
          ))}
        </div>
      </FeedScrollArea>
    </section>
  );
}
