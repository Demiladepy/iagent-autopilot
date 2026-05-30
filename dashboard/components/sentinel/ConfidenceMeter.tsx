"use client";

/** Gallery: Progress indicator / Meter — https://component.gallery/components/progress-indicator/ */

import { Progress } from "@/components/ui/progress";

type Props = {
  value: number;
  label?: string;
  className?: string;
};

export function ConfidenceMeter({ value, label = "Confidence", className }: Props) {
  const pct = Math.round(Math.min(1, Math.max(0, value)) * 100);

  return (
    <div className={className} role="meter" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
      <div className="mb-1 flex justify-between text-[10px] text-muted-foreground">
        <span>{label}</span>
        <span>{pct}%</span>
      </div>
      <Progress value={pct} />
    </div>
  );
}
