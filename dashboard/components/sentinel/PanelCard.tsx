import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/** Gallery: Card — grouped content surface */

type Props = {
  title?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  contentClassName?: string;
};

export function PanelCard({ title, children, className, contentClassName }: Props) {
  return (
    <Card className={cn("workbench-card border-0 bg-transparent shadow-none", className)}>
      {title != null && (
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold">{title}</CardTitle>
        </CardHeader>
      )}
      <CardContent className={cn(!title && "pt-6", contentClassName)}>{children}</CardContent>
    </Card>
  );
}
