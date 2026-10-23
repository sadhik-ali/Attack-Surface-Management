import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { Building2, Globe2, Plus, Search, ShieldAlert, Users } from "lucide-react";

import { PageHeader } from "@/components/common/PageHeader";
import { RiskBadge, StatusBadge } from "@/components/common/Badges";
import {
  Button,
  Card,
  CardContent,
  EmptyState,
  ErrorState,
  Input,
  Modal,
  Select,
  Skeleton,
  useToast,
} from "@/components/ui";
import { apiRequest, errorMessage } from "@/lib/api";
import type { CompanyDetail, CompanySummary } from "@/lib/apiTypes";
import { titleize } from "@/lib/labels";
import { formatNumber } from "@/lib/utils";
import { useAuth } from "@/context/AuthProvider";

const INDUSTRIES = [
  "technology",
  "financial_services",
  "healthcare",
  "retail",
  "manufacturing",
  "public_sector",
  "energy",
  "education",
  "logistics",
  "other",
];

type CompanyForm = {
  name: string;
  industry: string;
  website: string;
  contact_name: string;
  contact_email: string;
  root_domains: string;
  tags: string;
};

const EMPTY_FORM: CompanyForm = {
  name: "",
  industry: "technology",
  website: "",
  contact_name: "",
  contact_email: "",
  root_domains: "",
  tags: "",
};

export function CompaniesPage() {
  const { user, selectCompany, refreshMe } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [search, setSearch] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [form, setForm] = useState<CompanyForm>(EMPTY_FORM);
  const [formError, setFormError] = useState<string | null>(null);

  const companiesQuery = useQuery({
    queryKey: ["companies"],
    queryFn: () => apiRequest<CompanySummary[]>("/companies"),
  });

  const createMutation = useMutation({
    mutationFn: (payload: CompanyForm) =>
      apiRequest<CompanyDetail>("/companies", {
        method: "POST",
        body: {
          name: payload.name.trim(),
          industry: payload.industry,
          website: payload.website.trim() || null,
          contact_name: payload.contact_name.trim() || null,
          contact_email: payload.contact_email.trim() || null,
          root_domains: payload.root_domains
            .split(",")
            .map((domain) => domain.trim().toLowerCase())
            .filter(Boolean),
          tags: payload.tags
            .split(",")
            .map((tag) => tag.trim())
            .filter(Boolean),
        },
      }),
    onSuccess: async (company) => {
      toast({ title: "Company created", description: "An empty scan policy was created for this tenant.", variant: "success" });
      setCreateOpen(false);
      setForm(EMPTY_FORM);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["companies"] }),
        refreshMe(),
      ]);
      selectCompany(company.id);
      navigate("/dashboard");
    },
    onError: (error) => setFormError(errorMessage(error)),
  });

  const companies = companiesQuery.data ?? [];
  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return companies;
    return companies.filter(
      (company) =>
        company.name.toLowerCase().includes(term) ||
        company.slug.toLowerCase().includes(term) ||
        company.industry.toLowerCase().includes(term),
    );
  }, [companies, search]);

  const totalAssets = companies.reduce((sum, company) => sum + company.asset_count, 0);
  const activeCount = companies.filter((company) => company.status === "active").length;
  const highestRisk = companies.reduce((max, company) => Math.max(max, company.risk_score), 0);
  const isPlatformAdmin = user?.role_code === "super_admin";

  return (
    <div>
      <PageHeader
        title="Companies"
        description={
          isPlatformAdmin
            ? "Every tenant on the platform. Cross-company visibility is restricted to platform administrators."
            : "The companies you have been granted access to. Inventory, findings and users are isolated per company."
        }
        actions={
          isPlatformAdmin ? (
            <Button
              size="sm"
              onClick={() => {
                setFormError(null);
                setCreateOpen(true);
              }}
            >
              <Plus aria-hidden="true" className="h-4 w-4" />
              New company
            </Button>
          ) : null
        }
      />

      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <div className="metric-card">
          <p className="text-xs uppercase tracking-wide text-slate-500">Companies</p>
          <p className="mt-1 text-2xl font-semibold text-slate-50">{formatNumber(companies.length)}</p>
          <p className="mt-1 text-xs text-slate-500">{activeCount} active</p>
        </div>
        <div className="metric-card">
          <p className="text-xs uppercase tracking-wide text-slate-500">Assets in scope</p>
          <p className="mt-1 text-2xl font-semibold text-slate-50">{formatNumber(totalAssets)}</p>
          <p className="mt-1 text-xs text-slate-500">Across accessible tenants</p>
        </div>
        <div className="metric-card">
          <p className="text-xs uppercase tracking-wide text-slate-500">Highest risk score</p>
          <p className="mt-1 text-2xl font-semibold text-slate-50">{highestRisk.toFixed(1)}</p>
          <p className="mt-1 text-xs text-slate-500">Explainable 0–10 model</p>
        </div>
      </div>

      <div className="mb-4 flex items-center gap-2">
        <div className="relative w-full max-w-sm">
          <Search aria-hidden="true" className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search by name, slug or industry"
            className="pl-8"
            aria-label="Search companies"
          />
        </div>
      </div>

      {companiesQuery.isLoading ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 3 }).map((_, index) => (
            <Skeleton key={index} className="h-56" />
          ))}
        </div>
      ) : companiesQuery.isError ? (
        <ErrorState
          title="Could not load companies"
          message={errorMessage(companiesQuery.error)}
          onRetry={() => void companiesQuery.refetch()}
        />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={Building2}
          title={search ? "No matching companies" : "No companies yet"}
          description={
            search
              ? "Try a different name, slug or industry."
              : isPlatformAdmin
                ? "Create a tenant to begin managing its attack surface."
                : "Ask a platform administrator to add you to a company."
          }
          action={
            search ? (
              <Button variant="ghost" size="sm" onClick={() => setSearch("")}>
                Clear search
              </Button>
            ) : null
          }
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {filtered.map((company) => (
            <Card key={company.id} className="flex flex-col">
              <CardContent className="flex flex-1 flex-col gap-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex min-w-0 items-start gap-3">
                    <span className="mt-0.5 inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-brand-500/10 text-brand-400 ring-1 ring-brand-500/20">
                      <Building2 aria-hidden="true" className="h-5 w-5" />
                    </span>
                    <div className="min-w-0">
                      <p className="truncate text-base font-semibold text-slate-100">{company.name}</p>
                      <p className="truncate text-xs text-slate-500">
                        {titleize(company.industry)} · {company.slug}
                      </p>
                    </div>
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-1.5">
                    <RiskBadge score={company.risk_score} />
                    <StatusBadge status={company.status} />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3 text-xs">
                  <div className="rounded-md bg-surface-raised/60 px-3 py-2">
                    <p className="text-slate-500">Assets</p>
                    <p className="num mt-0.5 text-sm font-medium text-slate-200">{formatNumber(company.asset_count)}</p>
                  </div>
                  <div className="rounded-md bg-surface-raised/60 px-3 py-2">
                    <p className="text-slate-500">Risk score</p>
                    <p className="num mt-0.5 text-sm font-medium text-slate-200">{company.risk_score.toFixed(1)}</p>
                  </div>
                </div>

                <div className="flex flex-wrap gap-2 text-[11px] text-slate-500">
                  <span className="inline-flex items-center gap-1">
                    <Globe2 aria-hidden="true" className="h-3 w-3" />
                    {company.website ? company.website.replace(/^https?:\/\//, "") : "No website on record"}
                  </span>
                  {company.is_demo_tenant ? (
                    <span className="rounded bg-medium/10 px-1.5 py-0.5 font-medium text-medium">Demo tenant</span>
                  ) : null}
                </div>

                <div className="mt-auto flex items-center gap-2">
                  <Button
                    size="sm"
                    className="flex-1"
                    onClick={() => {
                      selectCompany(company.id);
                      navigate("/dashboard");
                    }}
                  >
                    <ShieldAlert aria-hidden="true" className="h-4 w-4" />
                    Open dashboard
                  </Button>
                  {isPlatformAdmin ? (
                    <Link to={`/users?company=${company.id}`} className="shrink-0">
                      <Button variant="ghost" size="sm" title="Manage members">
                        <Users aria-hidden="true" className="h-4 w-4" />
                        Members
                      </Button>
                    </Link>
                  ) : null}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Modal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="Create company"
        description="Creates an isolated tenant with a default scan policy. No scanning runs until an authorized scope is approved."
        size="lg"
        footer={
          <>
            <Button variant="ghost" size="sm" onClick={() => setCreateOpen(false)} disabled={createMutation.isPending}>
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={() => {
                setFormError(null);
                if (form.name.trim().length < 2) {
                  setFormError("Company name must be at least 2 characters");
                  return;
                }
                createMutation.mutate(form);
              }}
              disabled={createMutation.isPending}
            >
              {createMutation.isPending ? "Creating…" : "Create company"}
            </Button>
          </>
        }
      >
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            setFormError(null);
            if (form.name.trim().length < 2) {
              setFormError("Company name must be at least 2 characters");
              return;
            }
            createMutation.mutate(form);
          }}
        >
          {formError ? (
            <p role="alert" className="rounded-md border border-critical/30 bg-critical/10 px-3 py-2 text-xs text-critical">
              {formError}
            </p>
          ) : null}
          <div className="grid gap-4 sm:grid-cols-2">
            <Input
              label="Company name"
              required
              value={form.name}
              onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
              placeholder="Acme Holdings"
            />
            <Select
              label="Industry"
              value={form.industry}
              onChange={(event) => setForm((current) => ({ ...current, industry: event.target.value }))}
            >
              {INDUSTRIES.map((industry) => (
                <option key={industry} value={industry}>
                  {titleize(industry)}
                </option>
              ))}
            </Select>
            <Input
              label="Website"
              value={form.website}
              onChange={(event) => setForm((current) => ({ ...current, website: event.target.value }))}
              placeholder="https://acme.example"
            />
            <Input
              label="Contact email"
              type="email"
              value={form.contact_email}
              onChange={(event) => setForm((current) => ({ ...current, contact_email: event.target.value }))}
              placeholder="security@acme.example"
              hint="Use a monitored security contact where possible."
            />
            <Input
              label="Contact name"
              value={form.contact_name}
              onChange={(event) => setForm((current) => ({ ...current, contact_name: event.target.value }))}
              placeholder="Security lead"
            />
            <Input
              label="Tags"
              value={form.tags}
              onChange={(event) => setForm((current) => ({ ...current, tags: event.target.value }))}
              placeholder="production, eu-west"
              hint="Comma separated."
            />
          </div>
          <Input
            label="Root domains"
            value={form.root_domains}
            onChange={(event) => setForm((current) => ({ ...current, root_domains: event.target.value }))}
            placeholder="acme.example, acme-group.example"
            hint="Comma separated. Domains must still be verified through an approved authorization before any scan."
          />
          <p className="flex items-start gap-2 rounded-md bg-surface-raised/60 px-3 py-2 text-[11px] leading-relaxed text-slate-500">
            <ShieldAlert aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0 text-medium" />
            Creating a company does not grant permission to scan anything. Authorizations are approved separately and
            gate every discovery action.
          </p>
          <button type="submit" className="hidden" aria-hidden="true" tabIndex={-1} />
        </form>
      </Modal>
    </div>
  );
}

export default CompaniesPage;
