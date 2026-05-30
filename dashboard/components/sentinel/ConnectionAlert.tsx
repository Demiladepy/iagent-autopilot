"use client";

/** Gallery: Alert / Banner — https://component.gallery/components/alert/ */

import { WifiOff } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { useSentinelStore } from "@/lib/sentinel-store";

export function ConnectionAlert() {
  const connected = useSentinelStore((s) => s.connected);
  const runtimeOk = useSentinelStore((s) => s.runtime.ok);

  if (connected && runtimeOk) return null;

  const message =
    !runtimeOk && !connected
      ? "Runtime unreachable — start the API on port 8000, then refresh."
      : !connected
        ? "WebSocket reconnecting… decisions will resume when the stream is back."
        : "Runtime health check pending…";

  return (
    <Alert variant="warning" className="rounded-none border-x-0 border-t-0 border-amber-500/30 bg-amber-950/40">
      <WifiOff className="h-4 w-4" />
      <AlertDescription className="text-center">{message}</AlertDescription>
    </Alert>
  );
}
