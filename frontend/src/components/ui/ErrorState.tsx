import { TriangleAlert } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "./Button";

export type ErrorStateProps = {
  title?: string;
  message?: string;
  onRetry?: () => void;
  retryLabel?: string;
  className?: string;
};

export function ErrorState({
  title = "Request failed",
  message,
  onRetry,
  retryLabel = "Retry",
  className,
}: ErrorStateProps) {
  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col items-center justify-center gap-2 rounded-card border border-critical/30 bg-critical/10 px-6 py-10 text-center",
        className,
      )}
    >
      <TriangleAlert aria-hidden="true" className="h-6 w-6 text-critical" />
      <p className="text-sm font-medium text-slate-100">{title}</p>
      {message ? <p className="max-w-md text-xs text-slate-400">{message}</p> : null}
      {onRetry ? (
        <Button variant="ghost" size="sm" className="mt-2" onClick={onRetry}>
          {retryLabel}
        </Button>
      ) : null}
    </div>
  );
}
