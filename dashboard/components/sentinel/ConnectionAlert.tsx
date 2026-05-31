"use client";

/** Gallery: Alert / Banner — https://component.gallery/components/alert/ */

import { Loader2, RefreshCw, WifiOff } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { useSentinelStore } from "@/lib/sentinel-store";

export function ConnectionAlert() {
  const connected = useSentinelStore((s) => s.connected);
  const bootPhase = useSentinelStore((s) => s.bootPhase);
  const requestBootstrapRetry = useSentinelStore((s) => s.requestBootstrapRetry);

  if (bootPhase === "waking") {
    return (
      <Alert
        variant="default"
        className="rounded-none border-x-0 border-t-0 border-emerald-500/25 bg-emerald-950/30"
      >
        <Loader2 className="h-4 w-4 animate-spin text-emerald-400" />
        <AlertDescription className="text-center text-emerald-100/90">
          Waking the engine… (~30s on first load)
        </AlertDescription>
      </Alert>
    );
  }

  if (bootPhase === "failed") {
    return (
      <Alert
        variant="warning"
        className="rounded-none border-x-0 border-t-0 border-amber-500/30 bg-amber-950/40"
      >
        <WifiOff className="h-4 w-4" />
        <AlertDescription className="flex flex-wrap items-center justify-center gap-3 text-center">
          <span>
            Could not reach the runtime API — Render may still be starting, or the service is
            down.
          </span>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="h-8 gap-1.5 border-amber-500/40 text-amber-100 hover:bg-amber-500/15"
            onClick={() => requestBootstrapRetry()}
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Retry
          </Button>
        </AlertDescription>
      </Alert>
    );
  }

  if (!connected) {
    return (
      <Alert
        variant="warning"
        className="rounded-none border-x-0 border-t-0 border-amber-500/30 bg-amber-950/40"
      >
        <Loader2 className="h-4 w-4 animate-spin text-amber-300" />
        <AlertDescription className="text-center">
          Connecting live stream… decisions will appear as agents run.
        </AlertDescription>
      </Alert>
    );
  }

  return null;
}
