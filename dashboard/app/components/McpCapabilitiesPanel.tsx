"use client";

import { useState } from "react";
import { ChevronDown, Layers } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { PanelCard } from "@/components/sentinel";
import {
  countDemoExercisedTools,
  MCP_CAPABILITIES_TAGLINE,
  MCP_TOOL_CATEGORIES,
  MCP_TOOL_COUNT,
} from "@/lib/mcp-capabilities";
import { cn } from "@/lib/utils";

export function McpCapabilitiesPanel() {
  const [open, setOpen] = useState(false);
  const liveCount = countDemoExercisedTools();

  return (
    <PanelCard
      className="workbench-capabilities"
      contentClassName="!p-0"
      title={
        <button
          type="button"
          className="flex w-full items-center justify-between gap-2 text-left"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          aria-controls="mcp-capabilities-body"
        >
          <span className="inline-flex items-center gap-2">
            <Layers className="h-3.5 w-3.5 text-emerald-500/80" aria-hidden />
            MCP Capabilities
            <span className="font-mono text-[10px] font-normal text-neutral-500">
              {MCP_TOOL_COUNT} tools
            </span>
          </span>
          <ChevronDown
            className={cn(
              "h-4 w-4 shrink-0 text-neutral-500 transition-transform",
              open && "rotate-180"
            )}
            aria-hidden
          />
        </button>
      }
    >
      <div id="mcp-capabilities-body" className={cn(!open && "hidden")}>
        <div className="space-y-4 border-t border-white/[0.06] px-5 pb-5 pt-4">
          <p className="text-xs leading-relaxed text-neutral-400">{MCP_CAPABILITIES_TAGLINE}</p>

          <div className="flex flex-wrap gap-2 text-[10px]">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-emerald-300">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
              live · {liveCount} in demo
            </span>
            <span className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/[0.03] px-2 py-0.5 text-neutral-500">
              available · {MCP_TOOL_COUNT - liveCount} extensible
            </span>
          </div>

          <div className="max-h-[min(420px,50vh)] space-y-4 overflow-y-auto pr-1">
            {MCP_TOOL_CATEGORIES.map((category) => (
              <div key={category.id}>
                <p className="mb-2 font-mono text-[10px] uppercase tracking-[0.16em] text-neutral-600">
                  {category.label}
                </p>
                <ul className="flex flex-wrap gap-1.5">
                  {category.tools.map((t) => (
                    <li key={t.name}>
                      <span className="workbench-capability-chip inline-flex items-center gap-1.5 rounded-md border border-white/[0.08] bg-black/30 px-2 py-1 font-mono text-[10px] text-neutral-300">
                        {t.name}
                        {t.exercisedInDemo ? (
                          <Badge
                            variant="outline"
                            className="h-4 border-emerald-500/40 bg-emerald-500/15 px-1 py-0 text-[9px] font-medium uppercase tracking-wide text-emerald-300"
                          >
                            live
                          </Badge>
                        ) : (
                          <Badge
                            variant="outline"
                            className="h-4 border-white/10 bg-white/[0.03] px-1 py-0 text-[9px] font-medium uppercase tracking-wide text-neutral-500"
                          >
                            available
                          </Badge>
                        )}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      </div>
    </PanelCard>
  );
}
