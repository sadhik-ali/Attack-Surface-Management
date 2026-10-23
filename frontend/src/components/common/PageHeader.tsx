import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";

import { cn } from "@/lib/utils";

export type PageHeaderProps = {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  backTo?: string;
  backLabel?: string;
  className?: string;
};

export function PageHeader({
  title,
  description,
  actions,
  backTo,
  backLabel = "Back",
  className,
}: PageHeaderProps) {
  return (
    <div className={cn("mb-5 flex flex-col gap-3", className)}>
      {backTo ? (
        <Link
          to={backTo}
          className="inline-flex w-fit items-center gap-1.5 text-xs font-medium text-slate-400 transition-colors hover:text-brand-400"
        >
          <ArrowLeft aria-hidden="true" className="h-3.5 w-3.5" />
          {backLabel}
        </Link>
      ) : null}
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold tracking-tight text-slate-50 sm:text-2xl">
            {title}
          </h1>
          {description ? (
            <div className="mt-1 max-w-3xl text-sm text-slate-400">
              {description}
            </div>
          ) : null}
        </div>
        {actions ? (
          <div className="flex flex-wrap items-center gap-2">{actions}</div>
        ) : null}
      </div>
    </div>
  );
}
