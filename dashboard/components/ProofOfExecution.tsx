"use client";

import { useMemo, useState } from "react";
import { formatDistanceToNow } from "date-fns";
import { Check, Copy, ExternalLink } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  getProofOfExecution,
  truncateTxHash,
  type ProofOfExecutionRecord,
} from "@/lib/proof-of-execution";

function OnChainBadge() {
  return (
    <Badge className="bg-emerald-500/15 text-[10px] text-emerald-300 ring-1 ring-emerald-500/25">
      ON-CHAIN
    </Badge>
  );
}

function ProofContent({ proof }: { proof: ProofOfExecutionRecord }) {
  const [copied, setCopied] = useState(false);

  const relativeTime = useMemo(() => {
    if (!proof.timestampDate) return null;
    return formatDistanceToNow(proof.timestampDate, { addSuffix: true });
  }, [proof.timestampDate]);

  const fullTimestamp =
    proof.timestampDate?.toLocaleString(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    }) ?? proof.timestamp;

  async function copyHash() {
    try {
      await navigator.clipboard.writeText(proof.txHash);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard unavailable */
    }
  }

  const amountLabel =
    proof.amount && proof.asset ? `${proof.amount} ${proof.asset}` : proof.asset || "—";

  return (
    <div className="workbench-card workbench-proof rounded-2xl px-5 py-4 md:px-6 md:py-5">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-sm font-semibold tracking-tight text-white">Proof of Execution</h2>
        <OnChainBadge />
      </div>

      <p className="mt-2 text-xs leading-relaxed text-neutral-400">
        This agent has broadcast a real transaction on Injective testnet via the MCP server.
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <code
          className="min-w-0 flex-1 truncate font-mono text-xs text-emerald-200/90 sm:text-sm"
          title={proof.txHash}
        >
          {truncateTxHash(proof.txHash)}
        </code>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="h-8 shrink-0 gap-1.5 border-white/10 text-xs text-neutral-300 hover:border-emerald-500/30 hover:bg-emerald-500/10"
          onClick={() => void copyHash()}
          aria-label="Copy transaction hash"
        >
          {copied ? (
            <>
              <Check className="h-3.5 w-3.5 text-emerald-400" />
              Copied
            </>
          ) : (
            <>
              <Copy className="h-3.5 w-3.5" />
              Copy
            </>
          )}
        </Button>
      </div>

      <div className="mt-4">
        <a
          href={proof.explorerUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex h-9 items-center gap-2 rounded-md bg-emerald-500/15 px-4 text-sm font-medium text-emerald-200 ring-1 ring-emerald-500/25 transition-colors hover:bg-emerald-500/25"
        >
          Verify on Explorer
          <ExternalLink className="h-3.5 w-3.5" />
        </a>
      </div>

      <dl className="mt-4 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[10px] text-neutral-500">
        <div className="flex gap-1.5">
          <dt className="text-neutral-600">tool</dt>
          <dd className="text-neutral-400">{proof.tool}</dd>
        </div>
        <div className="flex gap-1.5">
          <dt className="text-neutral-600">amount</dt>
          <dd className="text-neutral-400">{amountLabel}</dd>
        </div>
        <div className="flex gap-1.5">
          <dt className="text-neutral-600">network</dt>
          <dd className="text-neutral-400">{proof.network}</dd>
        </div>
        {relativeTime ? (
          <div className="flex gap-1.5">
            <dt className="text-neutral-600">broadcast</dt>
            <dd className="text-neutral-400" title={fullTimestamp}>
              {relativeTime}
            </dd>
          </div>
        ) : null}
      </dl>

      <p className="mt-4 text-[11px] leading-relaxed text-neutral-600">
        The live pipeline runs in simulator / dry-run mode for judge safety. This is a verifiable record
        of a real testnet broadcast executed by the Executor agent through an Injective MCP write tool
        after Risk approval.
      </p>
    </div>
  );
}

function ProofEmpty() {
  return (
    <div className="workbench-card workbench-proof rounded-2xl border-dashed px-5 py-4 md:px-6 md:py-5">
      <h2 className="text-sm font-semibold tracking-tight text-neutral-400">Proof of Execution</h2>
      <p className="mt-2 text-xs text-neutral-600">No verified on-chain execution on record.</p>
    </div>
  );
}

/** Env-driven testnet receipt — no runtime / WebSocket dependency. */
export function ProofOfExecution() {
  const proof = useMemo(() => getProofOfExecution(), []);
  if (!proof) return <ProofEmpty />;
  return <ProofContent proof={proof} />;
}
