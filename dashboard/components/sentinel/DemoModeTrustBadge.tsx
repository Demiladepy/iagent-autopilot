"use client";

import { ShieldCheck } from "lucide-react";

/** Always-visible note for judges on the public deploy (simulator + dry-run). */
export function DemoModeTrustBadge() {
  return (
    <div
      className="flex items-center justify-center gap-2 border-t border-white/[0.06] bg-[#050505]/95 px-4 py-2.5 text-center"
      role="status"
      aria-live="polite"
    >
      <ShieldCheck className="h-3.5 w-3.5 shrink-0 text-emerald-500/80" aria-hidden />
      <p className="font-mono text-[10px] leading-relaxed text-neutral-400 sm:text-[11px]">
        Demo runs in{" "}
        <span className="text-emerald-400/90">simulator + dry-run</span> mode for safety — no live
        funds. Trades labeled DRY-RUN are intentional.
      </p>
    </div>
  );
}
