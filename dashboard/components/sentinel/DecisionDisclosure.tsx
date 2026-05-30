"use client";

/**
 * Gallery: Accordion / Disclosure + Timeline step content
 * https://component.gallery/components/accordion/
 * https://component.gallery/components/timeline/
 */

import {
  Activity,
  ArrowDown,
  Brain,
  ExternalLink,
  FileSearch,
  Shield,
  Zap,
  TrendingUp,
  AlertTriangle,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { ConfidenceMeter } from "@/components/sentinel/ConfidenceMeter";
import { txExplorerUrl } from "@/lib/explorer";
import { useSentinelStore } from "@/lib/sentinel-store";
import type { DecisionChain } from "@/lib/types";
import { cn } from "@/lib/utils";

const EVENT_ICONS: Record<string, React.ElementType> = {
  funding_flip: TrendingUp,
  drawdown: AlertTriangle,
  breakout: Activity,
  liquidation_cluster: AlertTriangle,
  position_drift: Activity,
  manual: Activity,
  synthetic: Activity,
};

function formatTime(ts: string | undefined) {
  if (!ts) return "—";
  return new Date(ts).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function flagVariant(flag: string): "default" | "destructive" | "secondary" | "outline" {
  const lower = flag.toLowerCase();
  if (lower.includes("drift") || lower.includes("slippage") || lower.includes("risk")) {
    return "destructive";
  }
  if (lower.includes("reversal") || lower.includes("warning")) return "secondary";
  return "outline";
}

type Props = {
  chain: DecisionChain;
  animate?: boolean;
  defaultOpen?: boolean;
};

export function DecisionDisclosure({ chain, animate, defaultOpen = true }: Props) {
  const network = useSentinelStore((s) => s.network);
  const { event, proposal, verdict, execution, audit } = chain;
  const EventIcon = EVENT_ICONS[event?.kind ?? ""] ?? Activity;
  const description =
    (event?.payload?.description as string) ||
    (event ? `${event.kind.replace(/_/g, " ")} · ${event.market}` : "Unknown trigger");

  return (
    <article
      className={cn(
        "workbench-card overflow-hidden rounded-2xl transition-colors hover:border-emerald-500/25",
        animate && "animate-slide-in-top"
      )}
    >
      <Accordion
        type="single"
        collapsible
        defaultValue={defaultOpen ? "pipeline" : undefined}
      >
        <AccordionItem value="pipeline" className="border-none">
          <AccordionTrigger className="border-b border-white/[0.06] px-4 py-3 hover:no-underline [&>svg]:hidden">
            <div className="flex flex-1 flex-wrap items-center gap-2 text-left">
              <span className="font-mono text-xs text-emerald-500/90">
                {formatTime(proposal.ts)}
              </span>
              <Badge variant="outline" className="border-emerald-500/40 text-emerald-400">
                {proposal.market ?? event?.market ?? "—"}
              </Badge>
              {verdict && (
                <Badge variant={verdict.approved ? "default" : "destructive"}>
                  {verdict.approved ? "Approved" : "Rejected"}
                </Badge>
              )}
            </div>
          </AccordionTrigger>
          <AccordionContent className="px-4 pb-0">
            <div className="space-y-0 py-3" role="list" aria-label="Decision pipeline">
              <PipelineStep icon={EventIcon} label="Market event" accent="text-sky-400">
                <p className="text-sm leading-relaxed text-slate-200">{description}</p>
                {event && (
                  <p className="mt-1 text-xs text-muted-foreground">
                    {event.kind} · {event.source} · {formatTime(event.ts)}
                  </p>
                )}
              </PipelineStep>
              <StepConnector />
              <PipelineStep icon={Brain} label="Analyst proposal" accent="text-violet-400">
                <p className="text-sm text-slate-300 line-clamp-3">{proposal.reasoning}</p>
                <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                  <Badge variant="secondary" className="capitalize">
                    {proposal.action}
                    {proposal.side ? ` ${proposal.side}` : ""}
                  </Badge>
                  {proposal.notional_usd != null && (
                    <span className="text-muted-foreground">${proposal.notional_usd} notional</span>
                  )}
                  {proposal.leverage != null && (
                    <span className="text-muted-foreground">{proposal.leverage}x lev</span>
                  )}
                </div>
                <ConfidenceMeter value={proposal.confidence} className="mt-2" />
              </PipelineStep>
              <StepConnector />
              <PipelineStep icon={Shield} label="Risk verdict" accent="text-amber-400">
                {verdict ? (
                  <>
                    <p
                      className={cn(
                        "text-sm font-medium",
                        verdict.approved ? "text-emerald-400" : "text-red-400"
                      )}
                    >
                      {verdict.approved ? "Approved for execution" : "Blocked"}
                    </p>
                    <ul className="mt-1 list-inside list-disc text-xs text-muted-foreground">
                      {verdict.reasons.slice(0, 4).map((r, i) => (
                        <li key={i}>{r}</li>
                      ))}
                    </ul>
                  </>
                ) : (
                  <p className="text-xs text-muted-foreground">Pending…</p>
                )}
              </PipelineStep>
              <StepConnector />
              <PipelineStep icon={Zap} label="Executor" accent="text-emerald-400">
                {execution ? (
                  <>
                    <Badge
                      variant={
                        execution.status === "success"
                          ? "default"
                          : execution.status === "failed"
                            ? "destructive"
                            : "secondary"
                      }
                    >
                      {execution.status}
                    </Badge>
                    {execution.tx_hash ? (
                      <div className="mt-2 flex flex-wrap items-center gap-2">
                        {execution.tx_hash.startsWith("dry-run-") ? (
                          <Badge variant="secondary" className="text-[10px]">
                            DRY-RUN
                          </Badge>
                        ) : (
                          <Badge className="bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-500/25 text-[10px]">
                            ON-CHAIN
                          </Badge>
                        )}
                        <a
                          href={
                            execution.tx_hash.startsWith("dry-run-")
                              ? txExplorerUrl(network, execution.tx_hash)
                              : `https://testnet.explorer.injective.network/transaction/${execution.tx_hash}`
                          }
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-xs text-emerald-400 hover:underline"
                        >
                          {execution.tx_hash.slice(0, 18)}…
                          <ExternalLink className="h-3 w-3" />
                        </a>
                      </div>
                    ) : null}
                  </>
                ) : (
                  <p className="text-xs text-muted-foreground">Pending…</p>
                )}
              </PipelineStep>
              <StepConnector />
              <PipelineStep icon={FileSearch} label="Auditor" accent="text-slate-300">
                {audit ? (
                  <>
                    <p className="text-sm leading-relaxed text-slate-300">{audit.summary}</p>
                    {audit.flags.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {audit.flags.map((f) => (
                          <Badge key={f} variant={flagVariant(f)} className="text-[10px]">
                            {f.replace(/_/g, " ")}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </>
                ) : (
                  <p className="text-xs text-muted-foreground">Awaiting audit…</p>
                )}
              </PipelineStep>
            </div>
          </AccordionContent>
        </AccordionItem>

        <AccordionItem value="raw" className="border-t border-white/[0.06]">
          <AccordionTrigger className="px-4 py-2 text-xs uppercase tracking-wider text-muted-foreground hover:no-underline">
            Raw JSON
          </AccordionTrigger>
          <AccordionContent className="bg-slate-950/80 px-4">
            <pre className="max-h-64 overflow-auto rounded-md bg-black/40 p-3 font-mono text-[11px] text-slate-400">
              {JSON.stringify(chain, null, 2)}
            </pre>
          </AccordionContent>
        </AccordionItem>
      </Accordion>
    </article>
  );
}

function PipelineStep({
  icon: Icon,
  label,
  accent,
  children,
}: {
  icon: React.ElementType;
  label: string;
  accent: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex gap-3 py-2" role="listitem">
      <div className={cn("mt-0.5 shrink-0", accent)}>
        <Icon className="h-4 w-4" aria-hidden />
      </div>
      <div className="min-w-0 flex-1">
        <p className={cn("text-[10px] font-semibold uppercase tracking-wider", accent)}>{label}</p>
        <div className="mt-1">{children}</div>
      </div>
    </div>
  );
}

function StepConnector() {
  return (
    <div className="ml-[7px] flex h-4 items-center" aria-hidden>
      <ArrowDown className="h-3 w-3 text-slate-600" />
    </div>
  );
}
