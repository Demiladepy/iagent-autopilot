/** Gallery: List — compact stacked rows */

import { cn } from "@/lib/utils";

export type DataListItem = {
  id: string;
  primary: React.ReactNode;
  secondary?: React.ReactNode;
  trailing?: React.ReactNode;
};

type Props = {
  items: DataListItem[];
  empty?: React.ReactNode;
  className?: string;
};

export function DataList({ items, empty, className }: Props) {
  if (items.length === 0) {
    return empty ? <div className="text-sm text-muted-foreground">{empty}</div> : null;
  }

  return (
    <ul className={cn("space-y-1.5", className)} role="list">
      {items.map((item) => (
        <li
          key={item.id}
          role="listitem"
          className="flex items-center justify-between gap-2 rounded-md border border-slate-800/60 bg-slate-950/40 px-2 py-1.5 text-xs"
        >
          <div className="min-w-0 flex-1">
            <div className="truncate">{item.primary}</div>
            {item.secondary && (
              <div className="truncate text-muted-foreground">{item.secondary}</div>
            )}
          </div>
          {item.trailing && <div className="shrink-0">{item.trailing}</div>}
        </li>
      ))}
    </ul>
  );
}
