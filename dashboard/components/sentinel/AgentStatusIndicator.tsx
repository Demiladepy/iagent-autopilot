/** Gallery: Status indicator — https://component.gallery/components/status-indicator/ */

import { cn } from "@/lib/utils";

const STATUS_STYLES: Record<string, string> = {
  running: "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.6)]",
  starting: "bg-amber-400",
  idle: "bg-amber-400",
  stopped: "bg-red-500",
  error: "bg-red-500",
};

type Props = {
  status: string;
  className?: string;
  title?: string;
};

export function AgentStatusIndicator({ status, className, title }: Props) {
  return (
    <span
      className={cn(
        "inline-block h-2.5 w-2.5 shrink-0 rounded-full",
        STATUS_STYLES[status] ?? STATUS_STYLES.idle,
        className
      )}
      title={title ?? status}
      role="status"
      aria-label={`Status: ${status}`}
    />
  );
}
