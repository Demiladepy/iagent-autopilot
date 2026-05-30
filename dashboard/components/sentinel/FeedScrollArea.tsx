/** Gallery: Scroll area — constrained feed regions */

import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";

type Props = {
  children: React.ReactNode;
  className?: string;
};

export function FeedScrollArea({ children, className }: Props) {
  return <ScrollArea className={cn("pr-3", className)}>{children}</ScrollArea>;
}
