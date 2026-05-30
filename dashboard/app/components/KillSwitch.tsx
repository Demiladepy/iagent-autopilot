"use client";

import { useState } from "react";
import { OctagonAlert } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { PanelCard } from "@/components/sentinel";
import { useSentinelStore } from "@/lib/sentinel-store";

export function KillSwitch() {
  const enabled = useSentinelStore((s) => s.portfolio.kill_switch);
  const setKillSwitch = useSentinelStore((s) => s.setKillSwitch);
  const [loading, setLoading] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);

  async function applyToggle() {
    setLoading(true);
    setConfirmOpen(false);
    try {
      const path = enabled ? "/api/proxy/resume" : "/api/proxy/kill";
      await fetch(path, { method: "POST" });
      setKillSwitch(!enabled);
      toast.success(enabled ? "Trading resumed" : "Kill switch engaged");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <PanelCard
        className={enabled ? "border-red-500/40 !shadow-[0_0_40px_-12px_rgba(239,68,68,0.25)]" : undefined}
        contentClassName="space-y-4"
        title={
          <span className="flex items-center gap-2">
            <OctagonAlert className={enabled ? "h-4 w-4 text-red-400" : "h-4 w-4 text-neutral-500"} />
            Human-in-the-loop · Kill switch
          </span>
        }
      >
        <p className="text-xs text-neutral-500">
          {enabled ? "All execution halted" : "Executor may run when risk approves"}
        </p>
        <Button
          variant={enabled ? "outline" : "destructive"}
          size="lg"
          className="h-12 w-full text-sm font-semibold uppercase tracking-wide"
          onClick={() => setConfirmOpen(true)}
          disabled={loading}
        >
          {loading ? "…" : enabled ? "Resume trading" : "Stop all trading"}
        </Button>
      </PanelCard>

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{enabled ? "Resume trading?" : "Engage kill switch?"}</DialogTitle>
            <DialogDescription>
              {enabled
                ? "Executor will accept new approved orders again."
                : "This immediately blocks the executor from opening or adjusting positions. Watcher and risk continue."}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2 sm:gap-2">
            <Button variant="outline" className="flex-1" onClick={() => setConfirmOpen(false)}>
              Discard
            </Button>
            <Button
              variant={enabled ? "default" : "destructive"}
              className="flex-1"
              onClick={applyToggle}
            >
              Approve
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
