import type { ReactNode } from "react";
import { Link, Navigate, Route, Routes } from "react-router-dom";
import { ShieldX } from "lucide-react";

import { useAuth } from "@/context/AuthProvider";
import { AppShell, RequireAuth } from "@/components/layout/AppShell";
import { LoginPage } from "@/features/auth/LoginPage";
import DashboardPage from "@/features/dashboard/DashboardPage";
import CompaniesPage from "@/features/companies/CompaniesPage";
import AssetsPage from "@/features/assets/AssetsPage";
import AssetDetailPage from "@/features/assets/AssetDetailPage";
import DomainsPage from "@/features/inventory/DomainsPage";
import IpsPage from "@/features/inventory/IpsPage";
import ApisPage from "@/features/inventory/ApisPage";
import CloudPage from "@/features/inventory/CloudPage";
import CertificatesPage from "@/features/certificates/CertificatesPage";
import VulnerabilitiesPage from "@/features/vulnerabilities/VulnerabilitiesPage";
import FindingsPage from "@/features/findings/FindingsPage";
import ChangesPage from "@/features/changes/ChangesPage";
import AlertsPage from "@/features/alerts/AlertsPage";
import ReportsPage from "@/features/reports/ReportsPage";
import ScansPage from "@/features/scans/ScansPage";
import UsersPage from "@/features/users/UsersPage";
import SettingsPage from "@/features/settings/SettingsPage";
import NotFoundPage from "@/features/NotFoundPage";

function RequirePermission({
  permission,
  children,
}: {
  permission: string;
  children: ReactNode;
}) {
  const { can, selectedCompany } = useAuth();

  if (!can(permission)) {
    return (
      <div className="mx-auto max-w-2xl py-8">
        <div
          role="alert"
          className="rounded-card border border-critical/30 bg-surface p-6 shadow-panel"
        >
          <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-critical/30 bg-critical/10">
            <ShieldX aria-hidden="true" className="h-4 w-4 text-critical" />
          </span>
          <h1 className="mt-4 text-lg font-semibold text-slate-100">
            Your role cannot open this page
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            {selectedCompany
              ? `Your membership in ${selectedCompany.name} does not include the "${permission}" permission.`
              : `This page requires the "${permission}" permission.`}{" "}
            Ask a company administrator if you need access.
          </p>
          <Link
            to="/dashboard"
            className="btn btn-ghost mt-4 inline-flex h-9 items-center px-3.5 text-sm"
          >
            Back to dashboard
          </Link>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}

function guard(permission: string, element: ReactNode) {
  return (
    <RequirePermission permission={permission}>{element}</RequirePermission>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={guard("risk:read", <DashboardPage />)} />
        <Route path="/companies" element={guard("company:read", <CompaniesPage />)} />
        <Route path="/assets" element={guard("asset:read", <AssetsPage />)} />
        <Route
          path="/assets/:assetId"
          element={guard("asset:read", <AssetDetailPage />)}
        />
        <Route path="/domains" element={guard("asset:read", <DomainsPage />)} />
        <Route path="/ips" element={guard("asset:read", <IpsPage />)} />
        <Route path="/apis" element={guard("asset:read", <ApisPage />)} />
        <Route path="/cloud" element={guard("asset:read", <CloudPage />)} />
        <Route
          path="/certificates"
          element={guard("certificate:read", <CertificatesPage />)}
        />
        <Route
          path="/vulnerabilities"
          element={guard("vulnerability:read", <VulnerabilitiesPage />)}
        />
        <Route path="/findings" element={guard("finding:read", <FindingsPage />)} />
        <Route path="/changes" element={guard("change:read", <ChangesPage />)} />
        <Route path="/alerts" element={guard("alert:read", <AlertsPage />)} />
        <Route path="/reports" element={guard("report:read", <ReportsPage />)} />
        <Route path="/scans" element={guard("scan:read", <ScansPage />)} />
        <Route path="/users" element={guard("user:read", <UsersPage />)} />
        <Route path="/settings" element={guard("company:read", <SettingsPage />)} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
