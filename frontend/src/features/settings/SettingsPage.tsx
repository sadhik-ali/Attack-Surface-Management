import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Building2,
  CloudOff,
  Database,
  KeyRound,
  Plug,
  ScrollText,
  Settings2,
  ShieldCheck,
} from "lucide-react";

import { PageHeader } from "@/components/common/PageHeader";
import { TableLoading } from "@/components/common/TableState";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  EmptyState,
  ErrorState,
  Input,
  Pagination,
  Select,
  Skeleton,
  Table,
  TBody,
  Td,
  Th,
  THead,
  Tr,
  Tabs,
  useToast,
} from "@/components/ui";
import { apiRequest, errorMessage } from "@/lib/api";
import type {
  AuditLogRow,
  CompanyDetail,
  Integration,
  Page,
  PlatformSettings,
} from "@/lib/apiTypes";
import { titleize } from "@/lib/labels";
import { formatDateTime, formatNumber } from "@/lib/utils";
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

const STATUS_OPTIONS = ["active", "suspended", "archived"];

type ProfileForm = {
  name: string;
  description: string;
  industry: string;
  website: string;
  contact_email: string;
  contact_name: string;
  root_domains: string;
  tags: string;
  status: string;
};

const EMPTY_PROFILE: ProfileForm = {
  name: "",
  description: "",
  industry: "technology",
  website: "",
  contact_email: "",
  contact_name: "",
  root_domains: "",
  tags: "",
  status: "active",
};

function profileFromCompany(company: CompanyDetail): ProfileForm {
  return {
    name: company.name,
    description: company.description ?? "",
    industry: company.industry,
    website: company.website ?? "",
    contact_email: company.contact_email ?? "",
    contact_name: company.contact_name ?? "",
    root_domains: company.root_domains.join(", "),
    tags: company.tags.join(", "),
    status: company.status,
  };
}

const INTEGRATION_TONE: Record<string, "low" | "medium" | "neutral" | "critical"> = {
  ready: "low",
  degraded: "medium",
  disabled: "neutral",
  unconfigured: "neutral",
  error: "critical",
};

export function SettingsPage() {
  const { selectedCompanyId, user, can, refreshMe } = useAuth();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const isSuperAdmin = user?.role_code === "super_admin";

  const canReadIntegrations = can("integration:read");
  const canReadAudit = can("audit:read");

  const TABS = [
    { value: "profile", label: "Company profile", icon: <Building2 aria-hidden="true" className="h-3.5 w-3.5" /> },
    ...(canReadIntegrations
      ? [{ value: "integrations", label: "Integrations", icon: <Plug aria-hidden="true" className="h-3.5 w-3.5" /> }]
      : []),
    ...(canReadAudit
      ? [{ value: "audit", label: "Audit log", icon: <ScrollText aria-hidden="true" className="h-3.5 w-3.5" /> }]
      : []),
    ...(isSuperAdmin
      ? [{ value: "platform", label: "Platform", icon: <Settings2 aria-hidden="true" className="h-3.5 w-3.5" /> }]
      : []),
  ] as const;

  type TabValue = (typeof TABS)[number]["value"];

  const [tab, setTab] = useState<TabValue>("profile");
  const [form, setForm] = useState<ProfileForm>(EMPTY_PROFILE);
  const [auditOutcome, setAuditOutcome] = useState("");
  const [auditPage, setAuditPage] = useState(1);
  const [auditPageSize] = useState(25);

  const companyQuery = useQuery({
    queryKey: ["company", selectedCompanyId],
    queryFn: () =>
      apiRequest<CompanyDetail>(`/companies/${selectedCompanyId}`),
    enabled: Boolean(selectedCompanyId),
  });

  const integrationsQuery = useQuery({
    queryKey: ["integrations", selectedCompanyId],
    queryFn: () =>
      apiRequest<Integration[]>(
        `/companies/${selectedCompanyId}/integrations`,
      ),
    enabled: Boolean(selectedCompanyId) && tab === "integrations" && canReadIntegrations,
  });

  const auditQuery = useQuery({
    queryKey: ["audit-logs", selectedCompanyId, auditOutcome, auditPage, auditPageSize],
    queryFn: () =>
      apiRequest<Page<AuditLogRow>>(
        `/companies/${selectedCompanyId}/audit-logs`,
        {
          params: {
            outcome: auditOutcome || undefined,
            page: auditPage,
            page_size: auditPageSize,
          },
        },
      ),
    enabled: Boolean(selectedCompanyId) && tab === "audit" && canReadAudit,
    placeholderData: (previous) => previous,
  });

  const platformQuery = useQuery({
    queryKey: ["platform-settings"],
    queryFn: () => apiRequest<PlatformSettings>("/meta/settings"),
    enabled: tab === "platform" && isSuperAdmin,
  });

  useEffect(() => {
    if (companyQuery.data) setForm(profileFromCompany(companyQuery.data));
  }, [companyQuery.data]);

  const saveMutation = useMutation({
    mutationFn: (payload: Partial<CompanyDetail>) =>
      apiRequest<CompanyDetail>(`/companies/${selectedCompanyId}`, {
        method: "PATCH",
        body: payload,
      }),
    onSuccess: async (updated) => {
      toast({ title: "Company profile saved", description: updated.name, variant: "success" });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["company", selectedCompanyId] }),
        queryClient.invalidateQueries({ queryKey: ["companies"] }),
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
        refreshMe(),
      ]);
    },
    onError: (error) =>
      toast({
        title: "Could not save company profile",
        description: errorMessage(error),
        variant: "error",
      }),
  });

  if (!selectedCompanyId) return null;

  const company = companyQuery.data;
  const canEdit = can("company:write");

  const submitProfile = () => {
    if (!form.name.trim() || form.name.trim().length < 2) {
      toast({ title: "Company name must be at least 2 characters", variant: "error" });
      return;
    }
    saveMutation.mutate({
      name: form.name.trim(),
      description: form.description.trim() || null,
      industry: form.industry,
      website: form.website.trim() || null,
      contact_email: form.contact_email.trim() || null,
      contact_name: form.contact_name.trim() || null,
      status: form.status,
      root_domains: form.root_domains
        .split(/[\s,]+/)
        .map((value) => value.trim().toLowerCase())
        .filter(Boolean),
      tags: form.tags
        .split(/[\s,]+/)
        .map((value) => value.trim())
        .filter(Boolean),
    } as Partial<CompanyDetail>);
  };

  const integrations = integrationsQuery.data ?? [];
  const implementedIntegrations = integrations.filter((entry) => entry.implemented);
  const unavailableIntegrations = integrations.filter((entry) => !entry.implemented);

  return (
    <div>
      <PageHeader
        title="Settings & integrations"
        description="Company identity, discovery integration status, tenant audit history and platform configuration. Cloud provider integrations are not implemented."
      />

      <Tabs
        value={tab}
        onValueChange={(value) => setTab(value as TabValue)}
        items={TABS.map((item) => ({
          value: item.value,
          label: item.label,
          icon: item.icon,
          content: null,
        }))}
        className="mb-4"
      />

      {tab === "profile" ? (
        <div className="grid gap-4 xl:grid-cols-3">
          <Card className="xl:col-span-2">
            <CardHeader>
              <CardTitle>Company profile</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {companyQuery.isLoading ? (
                <div className="grid gap-3 sm:grid-cols-2">
                  <Skeleton className="h-16" />
                  <Skeleton className="h-16" />
                  <Skeleton className="h-16" />
                  <Skeleton className="h-16" />
                </div>
              ) : companyQuery.isError ? (
                <ErrorState
                  title="Could not load company profile"
                  message={errorMessage(companyQuery.error)}
                  onRetry={() => void companyQuery.refetch()}
                />
              ) : (
                <>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Input
                      label="Company name"
                      value={form.name}
                      onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
                      disabled={!canEdit}
                      maxLength={200}
                    />
                    <Select
                      label="Industry"
                      value={form.industry}
                      onChange={(event) => setForm((current) => ({ ...current, industry: event.target.value }))}
                      disabled={!canEdit}
                    >
                      {INDUSTRIES.map((industry) => (
                        <option key={industry} value={industry}>{titleize(industry)}</option>
                      ))}
                    </Select>
                    <Input
                      label="Website"
                      value={form.website}
                      onChange={(event) => setForm((current) => ({ ...current, website: event.target.value }))}
                      disabled={!canEdit}
                      placeholder="https://example.com"
                    />
                    <Select
                      label="Status"
                      value={form.status}
                      onChange={(event) => setForm((current) => ({ ...current, status: event.target.value }))}
                      disabled={!canEdit}
                      hint={form.status !== "active" ? "Suspended and archived companies cannot request scans." : undefined}
                    >
                      {STATUS_OPTIONS.map((status) => (
                        <option key={status} value={status}>{titleize(status)}</option>
                      ))}
                    </Select>
                    <Input
                      label="Contact name"
                      value={form.contact_name}
                      onChange={(event) => setForm((current) => ({ ...current, contact_name: event.target.value }))}
                      disabled={!canEdit}
                    />
                    <Input
                      label="Contact email"
                      type="email"
                      value={form.contact_email}
                      onChange={(event) => setForm((current) => ({ ...current, contact_email: event.target.value }))}
                      disabled={!canEdit}
                    />
                    <Input
                      label="Root domains"
                      value={form.root_domains}
                      onChange={(event) => setForm((current) => ({ ...current, root_domains: event.target.value }))}
                      disabled={!canEdit}
                      placeholder="example.com, example.net"
                      hint="Comma-separated. These are identity hints; scans still require approved authorization records."
                    />
                    <Input
                      label="Tags"
                      value={form.tags}
                      onChange={(event) => setForm((current) => ({ ...current, tags: event.target.value }))}
                      disabled={!canEdit}
                      placeholder="production, pci, crown-jewel"
                    />
                  </div>
                  <div>
                    <label htmlFor="company-description" className="mb-1 block text-xs font-medium text-slate-300">
                      Description
                    </label>
                    <textarea
                      id="company-description"
                      value={form.description}
                      onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))}
                      rows={3}
                      maxLength={2000}
                      disabled={!canEdit}
                      className="w-full rounded-md border border-border bg-surface px-3 py-2 text-xs text-slate-200 placeholder:text-slate-600 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 disabled:cursor-not-allowed disabled:opacity-60"
                    />
                  </div>
                  <Button onClick={submitProfile} loading={saveMutation.isPending} disabled={!canEdit}>
                    Save company profile
                  </Button>
                  {!canEdit ? (
                    <p className="text-[11px] text-slate-500">
                      Company profile changes require the platform-level <span className="num">company:write</span> permission, held by Super Admins.
                    </p>
                  ) : null}
                </>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Tenant summary</CardTitle>
            </CardHeader>
            <CardContent>
              {company ? (
                <div className="space-y-2 text-xs">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-slate-500">Slug</span>
                    <span className="num text-slate-300">{company.slug}</span>
                  </div>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-slate-500">Status</span>
                    <Badge tone={company.status === "active" ? "low" : "medium"}>{titleize(company.status)}</Badge>
                  </div>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-slate-500">Assets</span>
                    <span className="num text-slate-300">{formatNumber(company.asset_count)}</span>
                  </div>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-slate-500">Members</span>
                    <span className="num text-slate-300">{formatNumber(company.member_count)}</span>
                  </div>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-slate-500">Open findings</span>
                    <span className="num text-slate-300">{formatNumber(company.open_findings)}</span>
                  </div>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-slate-500">Approved scopes</span>
                    <span className="num text-slate-300">{formatNumber(company.authorized_scope_count)}</span>
                  </div>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-slate-500">Last scan</span>
                    <span className="text-slate-300">{company.last_scan_at ? formatDateTime(company.last_scan_at) : "Never"}</span>
                  </div>
                  {company.is_demo_tenant ? (
                    <div className="mt-2 rounded-md border border-medium/30 bg-medium/10 px-2 py-1.5 text-[11px] text-medium">
                      Demonstration tenant. Rows prefixed as sample data are fixtures, not live observations.
                    </div>
                  ) : null}
                </div>
              ) : (
                <Skeleton className="h-32" />
              )}
            </CardContent>
          </Card>
        </div>
      ) : null}

      {tab === "integrations" ? (
        <div className="space-y-4">
          <Card>
            <CardContent className="flex gap-2 text-xs text-slate-400">
              <CloudOff aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-medium" />
              <p>
                <span className="font-medium text-slate-200">Cloud integrations are not implemented.</span>{" "}
                AWS, Azure and GCP inventory cannot be collected, no cloud credentials are stored, and cloud
                resources shown elsewhere in the product are labelled sample data. No secret values are displayed here.
              </p>
            </CardContent>
          </Card>

          {integrationsQuery.isLoading ? (
            <Card><CardContent><TableLoading columns={4} rows={4} /></CardContent></Card>
          ) : integrationsQuery.isError ? (
            <Card>
              <CardContent>
                <ErrorState
                  title="Could not load integration status"
                  message={errorMessage(integrationsQuery.error)}
                  onRetry={() => void integrationsQuery.refetch()}
                />
              </CardContent>
            </Card>
          ) : (
            <>
              <Card>
                <CardHeader><CardTitle>Built-in discovery capabilities</CardTitle></CardHeader>
                <CardContent>
                  {implementedIntegrations.length === 0 ? (
                    <EmptyState icon={Plug} title="No capability status reported" />
                  ) : (
                    <div className="grid gap-2 md:grid-cols-2">
                      {implementedIntegrations.map((integration) => (
                        <div key={integration.kind} className="rounded-md border border-border bg-surface-raised/40 p-3">
                          <div className="flex items-start justify-between gap-2">
                            <div>
                              <p className="text-sm font-medium text-slate-200">{integration.name}</p>
                              <p className="text-[11px] text-slate-500">{integration.capability}</p>
                            </div>
                            <Badge tone={INTEGRATION_TONE[integration.status] ?? "neutral"} dot>
                              {titleize(integration.status)}
                            </Badge>
                          </div>
                          <p className="mt-2 text-[11px] text-slate-500">{integration.description}</p>
                          <p className="mt-2 text-[11px] text-slate-600">
                            {integration.enabled ? "Enabled for this tenant" : "Currently disabled"}
                            {integration.last_run_at ? ` · last used ${formatDateTime(integration.last_run_at)}` : ""}
                          </p>
                          {integration.last_error ? (
                            <p className="mt-1 text-[11px] text-high">{integration.last_error}</p>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>

              <Card>
                <CardHeader><CardTitle>Not implemented</CardTitle></CardHeader>
                <CardContent>
                  <div className="grid gap-2 md:grid-cols-2">
                    {unavailableIntegrations.map((integration) => (
                      <div key={integration.kind} className="rounded-md border border-dashed border-border p-3">
                        <div className="flex items-start justify-between gap-2">
                          <p className="text-sm font-medium text-slate-300">{integration.name}</p>
                          <Badge tone="neutral">Not implemented</Badge>
                        </div>
                        <p className="mt-1 text-[11px] text-slate-500">{integration.description}</p>
                        {integration.secret_keys.length > 0 ? (
                          <p className="mt-1 text-[11px] text-slate-600">
                            Secret keys on record: {integration.secret_keys.join(", ")} (values never returned)
                          </p>
                        ) : null}
                      </div>
                    ))}
                  </div>
                  <p className="mt-3 text-[11px] text-slate-500">
                    These entries exist so the absence of a capability is explicit. They cannot be enabled from the UI.
                  </p>
                </CardContent>
              </Card>
            </>
          )}
        </div>
      ) : null}

      {tab === "audit" ? (
        <Card>
          <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
            <CardTitle>Tenant audit log</CardTitle>
            <Select
              aria-label="Outcome"
              value={auditOutcome}
              onChange={(event) => {
                setAuditOutcome(event.target.value);
                setAuditPage(1);
              }}
              className="w-40"
            >
              <option value="">All outcomes</option>
              <option value="success">Success</option>
              <option value="failure">Failure</option>
              <option value="denied">Denied</option>
            </Select>
          </CardHeader>
          <CardContent>
            {auditQuery.isLoading ? (
              <TableLoading columns={6} />
            ) : auditQuery.isError ? (
              <ErrorState
                title="Could not load audit log"
                message={errorMessage(auditQuery.error)}
                onRetry={() => void auditQuery.refetch()}
              />
            ) : (auditQuery.data?.items.length ?? 0) === 0 ? (
              <EmptyState
                icon={ScrollText}
                title="No audit events"
                description="Authentication, authorization, scan requests and administrative changes are recorded here."
              />
            ) : (
              <>
                <div className="overflow-x-auto rounded-md border border-border">
                  <Table>
                    <THead>
                      <Tr>
                        <Th>When</Th>
                        <Th>Actor</Th>
                        <Th>Action</Th>
                        <Th>Outcome</Th>
                        <Th className="hidden lg:table-cell">Object</Th>
                        <Th className="hidden xl:table-cell">IP</Th>
                      </Tr>
                    </THead>
                    <TBody>
                      {auditQuery.data?.items.map((entry) => (
                        <Tr key={entry.id}>
                          <Td><span className="text-xs text-slate-400">{formatDateTime(entry.created_at)}</span></Td>
                          <Td>
                            <p className="text-xs text-slate-300">{entry.actor_email ?? "system"}</p>
                            <p className="text-[11px] text-slate-500">{entry.actor_role ? titleize(entry.actor_role) : "—"}</p>
                          </Td>
                          <Td>
                            <span className="text-xs text-slate-400">{titleize(entry.action)}</span>
                            {entry.detail && Object.keys(entry.detail).length > 0 ? (
                              <p className="max-w-[16rem] truncate text-[10px] text-slate-600" title={JSON.stringify(entry.detail)}>
                                {JSON.stringify(entry.detail)}
                              </p>
                            ) : null}
                          </Td>
                          <Td>
                            <Badge tone={entry.outcome === "success" ? "low" : entry.outcome === "denied" ? "high" : "critical"} dot>
                              {titleize(entry.outcome)}
                            </Badge>
                          </Td>
                          <Td className="hidden lg:table-cell">
                            <span className="text-xs text-slate-400">
                              {entry.object_type ? `${titleize(entry.object_type)}${entry.object_label ? ` · ${entry.object_label}` : ""}` : "—"}
                            </span>
                          </Td>
                          <Td className="hidden xl:table-cell"><span className="num text-xs text-slate-500">{entry.ip_address ?? "—"}</span></Td>
                        </Tr>
                      ))}
                    </TBody>
                  </Table>
                </div>
                <Pagination
                  className="mt-3"
                  page={auditQuery.data?.page ?? auditPage}
                  total={auditQuery.data?.total}
                  pageSize={auditQuery.data?.page_size ?? auditPageSize}
                  onPageChange={setAuditPage}
                />
              </>
            )}
          </CardContent>
        </Card>
      ) : null}

      {tab === "platform" && isSuperAdmin ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Platform configuration</CardTitle>
            </CardHeader>
            <CardContent>
              {platformQuery.isLoading ? (
                <Skeleton className="h-40" />
              ) : platformQuery.isError ? (
                <ErrorState
                  title="Could not load platform settings"
                  message={errorMessage(platformQuery.error)}
                  onRetry={() => void platformQuery.refetch()}
                />
              ) : platformQuery.data ? (
                <div className="space-y-2 text-xs">
                  {[
                    ["Application", platformQuery.data.app_name],
                    ["Environment", platformQuery.data.app_env],
                    ["API prefix", platformQuery.data.api_prefix],
                    ["Job backend", platformQuery.data.job_backend],
                    ["Discovery enabled", platformQuery.data.discovery_enabled ? "Yes" : "No"],
                    ["Discovery offline", platformQuery.data.discovery_offline ? "Yes (active probing disabled)" : "No"],
                    ["Demo mode", platformQuery.data.demo_mode ? "Yes" : "No"],
                    ["Rate limiting", platformQuery.data.rate_limit_enabled ? `${platformQuery.data.rate_limit_requests_per_minute}/min` : "Disabled"],
                    ["Certificate warning", `${platformQuery.data.certificate_expiry_warning_days} days`],
                    ["Certificate critical", `${platformQuery.data.certificate_expiry_critical_days} days`],
                    ["Scan result retention", `${platformQuery.data.retention.scan_result_retention_days} days`],
                    ["Audit log retention", `${platformQuery.data.retention.audit_log_retention_days} days`],
                  ].map(([label, value]) => (
                    <div key={label} className="flex items-start justify-between gap-3 border-b border-border/60 pb-1.5 last:border-0">
                      <span className="text-slate-500">{label}</span>
                      <span className="num text-right text-slate-300">{value}</span>
                    </div>
                  ))}
                </div>
              ) : null}
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>Operational notes</CardTitle></CardHeader>
            <CardContent className="space-y-3 text-xs text-slate-400">
              <p className="flex gap-2">
                <ShieldCheck aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-400" />
                Platform settings are read-only here. Deployment configuration lives in environment variables, not in the database.
              </p>
              <p className="flex gap-2">
                <Database aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-500" />
                Retention values describe policy; purge jobs must be scheduled by the operator.
              </p>
              <p className="flex gap-2">
                <KeyRound aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-500" />
                Secret values are never returned by the API or written to logs.
              </p>
              <p className="flex gap-2">
                <Plug aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-500" />
                Supported built-in integrations: {platformQuery.data?.supported_integrations.join(", ") ?? "—"}.
              </p>
            </CardContent>
          </Card>
        </div>
      ) : null}
    </div>
  );
}

export default SettingsPage;
