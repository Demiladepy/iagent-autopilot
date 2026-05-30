import { cn } from "@/lib/utils";

type LogoProps = {
  /** Pixel width and height (square). */
  size?: number;
  className?: string;
  /** Set false when the wordmark beside the mark is sufficient. */
  showLabel?: boolean;
};

/** iAgent Autopilot propeller mark — source: /public/logo.svg */
export function Logo({ size = 36, className, showLabel = false }: LogoProps) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src="/logo.svg"
        alt="iAgent Autopilot"
        width={size}
        height={size}
        className="shrink-0 rounded-[22%]"
        aria-hidden={showLabel ? true : undefined}
      />
      {showLabel ? (
        <span className="text-sm font-semibold tracking-tight text-white">iAgent Autopilot</span>
      ) : null}
    </span>
  );
}
