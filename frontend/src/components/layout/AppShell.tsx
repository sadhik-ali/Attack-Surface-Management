import { useEffect, useState } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { ShieldHalf } from "lucide-react";

import { useAuth } from "@/context/AuthProvider";
import { findNavItem } from "@/config/navigation";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import { CompanySwitcher } from "./CompanySwitcher";
import { NotificationsMenu } from "./NotificationsMenu";
import { AccountMenu } from "./AccountMenu";
import { Button, Spinner } from "@/components/ui";

const COLLAPSE_KEY = "asm.sidebar_collapsed";

export function AppShell() {
  const { companies, logout } = useAuth();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem(COLLAPSE_KEY) === "true",
  );
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  const toggleCollapsed = () => {
    setCollapsed((current) => {
      localStorage.setItem(COLLAPSE_KEY, String(!current));
      return !current;
    });
  };

  if (companies.length === 0) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 px-6 text-center">
        <ShieldHalf aria-hidden="true" className="h-10 w-10 text-brand-500" />
        <div>
          <h1 className="text-lg font-semibold text-slate-100">
            No company access yet
          </h1>
          <p className="mt-1 max-w-md text-sm text-slate-400">
            Your account is active, but it is not a member of any company.
            Ask a company administrator to grant you access.
          </p>
        </div>
        <Button variant="ghost" onClick={() => void logout()}>
          Sign out
        </Button>
      </div>
    );
  }

  const title = findNavItem(location.pathname)?.label ?? "Workspace";

  return (
    <div className="flex h-screen overflow-hidden bg-bg">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-[70] focus:rounded-md focus:bg-brand-500 focus:px-3 focus:py-2 focus:text-sm focus:font-medium focus:text-white"
      >
        Skip to content
      </a>

      <Sidebar
        collapsed={collapsed}
        onToggleCollapsed={toggleCollapsed}
        className="hidden lg:flex"
      />

      {mobileOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            aria-label="Close navigation"
            className="absolute inset-0 bg-black/60"
            onClick={() => setMobileOpen(false)}
          />
          <div className="absolute inset-y-0 left-0 w-64 shadow-overlay">
            <Sidebar
              collapsed={false}
              onToggleCollapsed={() => setMobileOpen(false)}
            />
          </div>
        </div>
      ) : null}

      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar
          title={title}
          onToggleMobileNav={() => setMobileOpen(true)}
          companySwitcher={<CompanySwitcher />}
          notifications={<NotificationsMenu />}
          account={<AccountMenu />}
        />
        <main
          id="main-content"
          className="min-h-0 flex-1 overflow-y-auto"
          tabIndex={-1}
        >
          <div className="mx-auto w-full max-w-[1600px] px-3 py-4 sm:px-4 lg:px-6 lg:py-6">
            <Outlet />
          </div>
          <footer className="mx-auto w-full max-w-[1600px] px-3 pb-4 text-[11px] text-slate-600 sm:px-4 lg:px-6">
            Records labelled “Sample data” are demonstration fixtures. They are
            not live scan output. Live rows are labelled “Observed live”.
          </footer>
        </main>
      </div>
    </div>
  );
}

export function AuthLoadingScreen() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-bg">
      <ShieldHalf aria-hidden="true" className="h-9 w-9 text-brand-500" />
      <div className="flex items-center gap-2 text-sm text-slate-400">
        <Spinner className="h-4 w-4" />
        Loading your workspace…
      </div>
    </div>
  );
}

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { status } = useAuth();
  const location = useLocation();

  if (status === "loading") return <AuthLoadingScreen />;
  if (status === "anonymous") {
    return (
      <Navigate
        to="/login"
        replace
        state={{ from: `${location.pathname}${location.search}` }}
      />
    );
  }
  return <>{children}</>;
}
