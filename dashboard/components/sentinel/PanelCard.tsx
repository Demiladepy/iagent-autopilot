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
        <CardHeader className="px-5 pb-2 pt-5">
          <CardTitle className="text-sm font-semibold text-neutral-200">{title}</CardTitle>
        </CardHeader>
      )}
      <CardContent className={cn("px-5 pb-5", !title && "pt-6", contentClassName)}>
        {children}
      </CardContent>
    </Card>
  );
}
