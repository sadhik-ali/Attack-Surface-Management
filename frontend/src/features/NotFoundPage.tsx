import { Link, useLocation } from "react-router-dom";
import { Compass, LayoutDashboard } from "lucide-react";

import { PageHeader } from "@/components/common/PageHeader";

export default function NotFoundPage() {
  const location = useLocation();

  return (
    <div className="mx-auto max-w-2xl py-8">
      <PageHeader
        title="Page not found"
        description="The address does not match any page in this workspace. It may have been renamed or the link may be incomplete."
      />
      <div className="rounded-card border border-border bg-surface p-6 shadow-panel">
        <div className="flex items-start gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-border bg-surface-raised">
            <Compass aria-hidden="true" className="h-4 w-4 text-brand-400" />
          </span>
          <div className="min-w-0">
            <p className="text-sm font-medium text-slate-200">
              Nothing is routed here
            </p>
            <p className="num mt-1 break-all text-xs text-slate-500">
              {location.pathname}
            </p>
          </div>
        </div>
        <Link
          to="/dashboard"
          className="btn btn-primary mt-5 inline-flex h-9 items-center gap-2 px-3.5 text-sm"
        >
          <LayoutDashboard aria-hidden="true" className="h-4 w-4" />
          Return to dashboard
        </Link>
      </div>
    </div>
  );
}
