import { Menu } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui";

export type TopbarProps = {
  title: string;
  onToggleMobileNav: () => void;
  companySwitcher?: ReactNode;
  notifications?: ReactNode;
  account?: ReactNode;
  actions?: ReactNode;
  className?: string;
};

export function Topbar({
  title,
  onToggleMobileNav,
  companySwitcher,
  notifications,
  account,
  actions,
  className,
}: TopbarProps) {
  return (
    <header
      className={cn(
        "sticky top-0 z-30 flex h-14 shrink-0 items-center gap-2 border-b border-border bg-surface/95 px-3 backdrop-blur lg:px-6",
        className,
      )}
    >
      <Button
        variant="ghost"
        size="icon"
        className="lg:hidden"
        aria-label="Open navigation"
        onClick={onToggleMobileNav}
      >
        <Menu aria-hidden="true" className="h-4 w-4" />
      </Button>

      <p className="min-w-0 flex-1 truncate text-sm font-medium text-slate-400">
        <span className="hidden sm:inline">Security workspace</span>
        <span aria-hidden="true" className="mx-2 hidden text-slate-600 sm:inline">
          /
        </span>
        <span className="text-slate-200">{title}</span>
      </p>

      <div className="flex items-center gap-1.5 sm:gap-2">
        {actions}
        {companySwitcher}
        {notifications}
        {account}
      </div>
    </header>
  );
}
