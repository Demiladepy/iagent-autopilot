"use client";

import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import { Logo } from "@/components/Logo";
import { RuntimeStatus } from "@/app/components/RuntimeStatus";
import { cn } from "@/lib/utils";

type Props = {
  className?: string;
};

/** Dashboard top bar — ai.work workbench chrome */

export function WorkbenchHeader({ className }: Props) {
  return (
    <header
      className={cn(
        "sticky top-0 z-40 border-b border-white/[0.06] bg-[#050505]/90 backdrop-blur-xl",
        className
      )}
    >
      <div className="workbench-main mx-auto flex w-full flex-wrap items-center justify-between gap-4 py-3">
        <div className="flex min-w-0 items-center gap-4">
          <Link href="/" className="group flex items-center gap-3">
            <Logo size={36} className="shrink-0" />
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold tracking-tight text-white">
                iAgent Autopilot
              </p>
              <p className="truncate text-[10px] text-neutral-500">AI Worker for Injective trading</p>
            </div>
          </Link>
          <span className="hidden h-6 w-px bg-white/10 sm:block" aria-hidden />
          <RuntimeStatus />
        </div>
        <nav className="flex items-center gap-3 text-[10px] uppercase tracking-[0.18em] text-neutral-500">
          <span className="hidden text-neutral-600 md:inline">Workbench</span>
          <Link
            href="/"
            className="inline-flex items-center gap-1 border border-white/10 px-3 py-1.5 text-neutral-300 transition-colors hover:border-white/25 hover:text-white"
          >
            Home
            <ArrowUpRight className="h-3 w-3" />
          </Link>
        </nav>
      </div>
    </header>
  );
}
