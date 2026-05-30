"use client";

import { FileSearch } from "lucide-react";
import { PanelCard } from "@/components/sentinel";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { useSentinelStore } from "@/lib/sentinel-store";

export function AuditStream() {
  const stream = useSentinelStore((s) => s.auditStream);
  const lastAudit = useSentinelStore((s) => s.portfolio.last_audit);

  const text = stream?.text ?? lastAudit?.summary ?? "";
  const isLive = stream && !stream.done;

  if (!text && !isLive) return null;

  return (
    <PanelCard
      className="border-violet-500/20"
      title={
        <span className="flex items-center gap-2">
          <FileSearch className="h-4 w-4 text-violet-400" />
          Live audit stream
          {isLive && (
            <Badge variant="outline" className="animate-pulse-soft border-violet-400/50 text-[10px]">
              streaming
            </Badge>
          )}
        </span>
      }
      contentClassName="space-y-2"
    >
      <ScrollArea className="max-h-28">
        <p className="text-xs leading-relaxed text-neutral-300 whitespace-pre-wrap">{text}</p>
      </ScrollArea>
      {stream?.flags && stream.flags.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {stream.flags.map((f) => (
            <Badge key={f} variant="outline" className="text-[10px]">
              {f.replace(/_/g, " ")}
            </Badge>
          ))}
        </div>
      )}
    </PanelCard>
  );
}
