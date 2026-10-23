import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui";

export type StatTone = "brand" | "critical" | "high" | "medium" | "low" | "neutral";

const TONE_CLASSES: Record<StatTone, string> = {
  brand: "bg-brand-500/10 text-brand-400 ring-brand-500/20",
  critical: "bg-critical/10 text-critical ring-critical/20",
  high: "bg-high/10 text-high ring-high/20",
  medium: "bg-medium/10 text-medium ring-medium/20",
  low: "bg-low/10 text-low ring-low/20",
  neutral: "bg-surface-raised text-slate-400 ring-border",
};

export type StatCardProps = {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  icon?: LucideIcon;
  tone?: StatTone;
  loading?: boolean;
  className?: string;
};

export function StatCard({
  label,
  value,
  hint,
  icon: Icon,
  tone = "brand",
  loading = false,
  className,
}: StatCardProps) {
  return (
    <div className={cn("metric-card flex items-start gap-3", className)}>
      {Icon ? (
        <span
          className={cn(
            "mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ring-1",
            TONE_CLASSES[tone],
          )}
        >
          <Icon aria-hidden="true" className="h-4 w-4" />
        </span>
      ) : null}
      <div className="min-w-0 flex-1">
        <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
          {label}
        </p>
        {loading ? (
          <Skeleton className="mt-2 h-7 w-16" />
        ) : (
          <div className="mt-1 truncate text-2xl font-semibold tracking-tight text-slate-50">
            {value}
          </div>
        )}
        {hint ? (
          <div className="mt-1 truncate text-xs text-slate-500">{hint}</div>
        ) : null}
      </div>
    </div>
  );
}
