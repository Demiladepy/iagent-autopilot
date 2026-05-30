import { cn } from "@/lib/utils";

/** ai.work-style section index — e.g. 01 · Agent fleet */

type Props = {
  index: string;
  children: React.ReactNode;
  className?: string;
};

export function SectionLabel({ index, children, className }: Props) {
  return (
    <p
      className={cn(
        "font-mono text-[10px] uppercase tracking-[0.22em] text-neutral-500",
        className
      )}
    >
      <span className="text-neutral-600">{index}</span>
      <span className="mx-2 text-neutral-700">·</span>
      {children}
    </p>
  );
}
