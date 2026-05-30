"use client";

import { Activity, Link2, FlaskConical } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { useSentinelStore } from "@/lib/sentinel-store";

export function RuntimeStatus() {
  const runtime = useSentinelStore((s) => s.runtime);
  const network = useSentinelStore((s) => s.network);
  const connected = useSentinelStore((s) => s.connected);

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Badge variant="outline" className="gap-1 font-mono text-[10px] capitalize">
        <Activity className="h-3 w-3" />
        {network}
      </Badge>
      <Badge variant={connected ? "default" : "secondary"} className="font-mono text-[10px]">
        {connected ? "WS live" : "WS offline"}
      </Badge>
      <Badge
        variant={runtime.mcp_connected ? "default" : "outline"}
        className="gap-1 font-mono text-[10px]"
      >
        <Link2 className="h-3 w-3" />
        MCP {runtime.mcp_connected ? "on" : "off"}
      </Badge>
      {runtime.simulator_mode && (
        <Badge variant="secondary" className="gap-1 font-mono text-[10px]">
          <FlaskConical className="h-3 w-3" />
          Simulator
        </Badge>
      )}
    </div>
  );
}
