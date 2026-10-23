import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Ban,
  Check,
  ClipboardCheck,
  History,
  Play,
  Radar,
  RotateCcw,
  Settings2,
  ShieldCheck,
  X,
} from "lucide-react";

import { PageHeader } from "@/components/common/PageHeader";
import { SeverityBadge, StatusBadge } from "@/components/common/Badges";
import { TableLoading } from "@/components/common/TableState";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Checkbox,
  EmptyState,
  ErrorState,
  Input,
  Modal,
  Pagination,
  Select,
  Skeleton,
  Spinner,
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
  Authorization,
  Page,
  Scan,
  ScanCapability,
  ScanDetail,
  ScanPolicy,
} from "@/lib/apiTypes";
import { titleize } from "@/lib/labels";
import { cn, formatDateTime, formatNumber, relativeTime } from "@/lib/utils";
import { useAuth } from "@/context/AuthProvider";

const SCOPE_TYPES = [
  "domain",
  "wildcard_domain",
  "url",
  "ipv4",
  "ipv6",
  "cidr",
] as const;

const VERIFICATION_METHODS = [
  "dns_txt",
  "http_file",
  "whois_contact",
  "cloud_account",
  "signed_statement",
  "manual_review",
] as const;

const TABS = [
  { value: "new", label: "New scan", icon: <Play aria-hidden="true" className="h-3.5 w-3.5" /> },
  { value: "history", label: "Scan history", icon: <History aria-hidden="true" className="h-3.5 w-3.5" /> },
  { value: "authorizations", label: "Authorizations", icon: <ShieldCheck aria-hidden="true" className="h-3.5 w-3.5" /> },
  { value: "policy", label: "Scan policy", icon: <Settings2 aria-hidden="true" className="h-3.5 w-3.5" /> },
] as const;

type TabValue = (typeof TABS)[number]["value"];

const ACTIVE_STATUSES = ["queued", "running"];

type PolicyForm = {
  max_concurrency: string;
  requests_per_second: string;
  timeout_seconds: string;
  max_targets_per_run: string;
  allowed_ports: string;
  respect_robots: boolean;
  safe_mode: boolean;
  business_hours_only: boolean;
};

const POLICY_DEFAULTS: PolicyForm = {
  max_concurrency: "4",
  requests_per_second: "2",
  timeout_seconds: "300",
  max_targets_per_run: "25",
  allowed_ports: "80, 443",
  respect_robots: true,
  safe_mode: true,
  business_hours_only: false,
};

function policyToForm(policy: ScanPolicy): PolicyForm {
  return {
    max_concurrency: String(policy.max_concurrency),
    requests_per_second: String(policy.requests_per_second),
    timeout_seconds: String(policy.timeout_seconds),
    max_targets_per_run: String(policy.max_targets_per_run),
    allowed_ports: policy.allowed_ports.join(", "),
    respect_robots: policy.respect_robots,
    safe_mode: policy.safe_mode,
    business_hours_only: policy.business_hours_only,
  };
}

export function ScansPage() {
  const { selectedCompanyId, can, enums } = useAuth();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [searchParams, setSearchParams] = useSearchParams();

  const initialTarget = searchParams.get("target") ?? "";
  const initialScanId = searchParams.get("scan");

  const [tab, setTab] = useState<TabValue>(initialScanId ? "history" : "new");
  const [targetsText, setTargetsText] = useState(initialTarget);
  const [scanType, setScanType] = useState("passive_dns");
  const [scanName, setScanName] = useState("");
  const [includeSubdomains, setIncludeSubdomains] = useState(true);
  const [portsText, setPortsText] = useState("");
  const [authorizationId, setAuthorizationId] = useState("");
  const [confirmAuthorized, setConfirmAuthorized] = useState(false);
  const [selectedScanId, setSelectedScanId] = useState<string | null>(initialScanId);

  const [statusFilter, setStatusFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);

  const [scopeType, setScopeType] = useState<string>("domain");
  const [scopeValue, setScopeValue] = useState("");
  const [method, setMethod] = useState<string>("manual_review");
  const [allowActiveProbing, setAllowActiveProbing] = useState(false);
  const [maxPorts, setMaxPorts] = useState("100");
  const [expiresAt, setExpiresAt] = useState("");
  const [evidence, setEvidence] = useState("");
  const [notes, setNotes] = useState("");

  const [policyForm, setPolicyForm] = useState<PolicyForm>(POLICY_DEFAULTS);

  const capabilitiesQuery = useQuery({
    queryKey: ["scan-capabilities", selectedCompanyId],
    queryFn: () =>
      apiRequest<ScanCapability[]>(
        `/companies/${selectedCompanyId}/scans/capabilities`,
      ),
    enabled: Boolean(selectedCompanyId),
  });

  const policyQuery = useQuery({
    queryKey: ["scan-policy", selectedCompanyId],
    queryFn: () =>
      apiRequest<ScanPolicy>(`/companies/${selectedCompanyId}/scan-policy`),
    enabled: Boolean(selectedCompanyId),
  });

  const scansQuery = useQuery({
    queryKey: ["scans", selectedCompanyId, statusFilter, typeFilter, page, pageSize],
    queryFn: () =>
      apiRequest<Page<Scan>>(`/companies/${selectedCompanyId}/scans`, {
        params: {
          status_filter: statusFilter || undefined,
          scan_type: typeFilter || undefined,
          page,
          page_size: pageSize,
          sort: "created_at",
          order: "desc",
        },
      }),
    enabled: Boolean(selectedCompanyId) && tab === "history",
    placeholderData: (previous) => previous,
    refetchInterval: (query) => {
      const items = query.state.data?.items ?? [];
      return items.some((scan) => ACTIVE_STATUSES.includes(scan.status))
        ? 5_000
        : false;
    },
  });

  const scanDetailQuery = useQuery({
    queryKey: ["scan", selectedCompanyId, selectedScanId],
    queryFn: () =>
      apiRequest<ScanDetail>(
        `/companies/${selectedCompanyId}/scans/${selectedScanId}`,
      ),
    enabled: Boolean(selectedCompanyId) && Boolean(selectedScanId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && ACTIVE_STATUSES.includes(status) ? 4_000 : false;
    },
  });

  const authorizationsQuery = useQuery({
    queryKey: ["authorizations", selectedCompanyId],
    queryFn: () =>
      apiRequest<Authorization[]>(
        `/companies/${selectedCompanyId}/authorizations`,
      ),
    enabled: Boolean(selectedCompanyId),
  });

  useEffect(() => {
    if (policyQuery.data) setPolicyForm(policyToForm(policyQuery.data));
  }, [policyQuery.data]);

  const liveAuthorizations = (authorizationsQuery.data ?? []).filter(
    (authorization) => authorization.is_live,
  );

  const requestMutation = useMutation({
    mutationFn: (payload: {
      scan_type: string;
      targets: string[];
      authorization_record_id?: string;
      name?: string;
      include_subdomains: boolean;
      ports: number[];
      confirm_authorized: boolean;
    }) =>
      apiRequest<Scan>(`/companies/${selectedCompanyId}/scans`, {
        method: "POST",
        body: payload,
      }),
    onSuccess: async (scan) => {
      toast({
        title: "Scan queued",
        description: `${scan.name ?? titleize(scan.scan_type)} is now ${scan.status}.`,
        variant: "success",
      });
      setConfirmAuthorized(false);
      setSelectedScanId(scan.id);
      setTab("history");
      setSearchParams({ scan: scan.id }, { replace: true });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["scans"] }),
        queryClient.invalidateQueries({ queryKey: ["scan", selectedCompanyId, scan.id] }),
      ]);
    },
    onError: (error) =>
      toast({
        title: "Scan request refused",
        description: errorMessage(error),
        variant: "error",
        duration: 8000,
      }),
  });

  const cancelMutation = useMutation({
    mutationFn: (scanId: string) =>
      apiRequest<Scan>(
        `/companies/${selectedCompanyId}/scans/${scanId}/cancel`,
        { method: "POST" },
      ),
    onSuccess: async () => {
      toast({ title: "Scan cancelled", variant: "success" });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["scan", selectedCompanyId] }),
        queryClient.invalidateQueries({ queryKey: ["scans"] }),
      ]);
    },
    onError: (error) =>
      toast({
        title: "Could not cancel scan",
        description: errorMessage(error),
        variant: "error",
      }),
  });

  const authorizationMutation = useMutation({
    mutationFn: (payload: {
      scope_type: string;
      value: string;
      method: string;
      evidence?: string;
      notes?: string;
      expires_at?: string;
      allow_active_probing: boolean;
      max_ports_per_target: number;
    }) =>
      apiRequest<Authorization>(
        `/companies/${selectedCompanyId}/authorizations`,
        { method: "POST", body: payload },
      ),
    onSuccess: async () => {
      toast({
        title: "Authorization requested",
        description: "It stays pending until a different administrator approves it.",
        variant: "success",
      });
      setScopeValue("");
      setEvidence("");
      setNotes("");
      setExpiresAt("");
      setAllowActiveProbing(false);
      await queryClient.invalidateQueries({ queryKey: ["authorizations", selectedCompanyId] });
    },
    onError: (error) =>
      toast({
        title: "Could not create authorization",
        description: errorMessage(error),
        variant: "error",
      }),
  });

  const decisionMutation = useMutation({
    mutationFn: ({ id, decision }: { id: string; decision: "approved" | "rejected" }) =>
      apiRequest<Authorization>(
        `/companies/${selectedCompanyId}/authorizations/${id}/decision`,
        { method: "POST", body: { decision } },
      ),
    onSuccess: async (record) => {
      toast({
        title: `Authorization ${record.status}`,
        description: record.value,
        variant: "success",
      });
      await queryClient.invalidateQueries({ queryKey: ["authorizations", selectedCompanyId] });
    },
    onError: (error) =>
      toast({
        title: "Decision could not be recorded",
        description: errorMessage(error),
        variant: "error",
      }),
  });

  const policyMutation = useMutation({
    mutationFn: (payload: Partial<ScanPolicy>) =>
      apiRequest<ScanPolicy>(`/companies/${selectedCompanyId}/scan-policy`, {
        method: "PATCH",
        body: payload,
      }),
    onSuccess: async () => {
      toast({ title: "Scan policy updated", variant: "success" });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["scan-policy", selectedCompanyId] }),
        queryClient.invalidateQueries({ queryKey: ["scan-capabilities", selectedCompanyId] }),
      ]);
    },
    onError: (error) =>
      toast({
        title: "Could not update scan policy",
        description: errorMessage(error),
        variant: "error",
      }),
  });

  if (!selectedCompanyId) return null;

  const capabilities = capabilitiesQuery.data ?? [];
  const selectedCapability = capabilities.find(
    (capability) => capability.scan_type === scanType,
  );
  const policy = policyQuery.data;

  const openScan = (scanId: string) => {
    setSelectedScanId(scanId);
    const next = new URLSearchParams(searchParams);
    next.set("scan", scanId);
    setSearchParams(next, { replace: true });
  };

  const closeScan = () => {
    setSelectedScanId(null);
    const next = new URLSearchParams(searchParams);
    next.delete("scan");
    setSearchParams(next, { replace: true });
  };

  const submitScan = () => {
    const targets = targetsText
      .split(/[\n,]+/)
      .map((value) => value.trim())
      .filter(Boolean);
    if (targets.length === 0) {
      toast({ title: "Add at least one target", variant: "error" });
      return;
    }
    if (!confirmAuthorized) {
      toast({
        title: "Confirm authorization required",
        description: "Tick the confirmation that you are authorised to assess these targets.",
        variant: "error",
      });
      return;
    }
    const ports = portsText
      .split(/[\s,]+/)
      .map((value) => Number(value))
      .filter((value) => Number.isFinite(value) && value > 0);
    const active = selectedCapability?.intrusive ?? false;
    const selectedAuth = liveAuthorizations.find(
      (authorization) => authorization.id === authorizationId,
    );
    if (active && selectedAuth && !selectedAuth.allow_active_probing) {
      toast({
        title: "Selected authorization is passive-only",
        description: "Choose another record or allow active probing on that record.",
        variant: "error",
      });
      return;
    }
    requestMutation.mutate({
      scan_type: scanType,
      targets,
      authorization_record_id: authorizationId || undefined,
      name: scanName.trim() || undefined,
      include_subdomains: includeSubdomains,
      ports,
      confirm_authorized: confirmAuthorized,
    });
  };

  const submitAuthorization = () => {
    if (!scopeValue.trim()) {
      toast({ title: "Enter a scope value", variant: "error" });
      return;
    }
    const parsedMaxPorts = Number(maxPorts);
    if (!Number.isFinite(parsedMaxPorts) || parsedMaxPorts < 1 || parsedMaxPorts > 1000) {
      toast({ title: "Max ports per target must be between 1 and 1000", variant: "error" });
      return;
    }
    authorizationMutation.mutate({
      scope_type: scopeType,
      value: scopeValue.trim(),
      method,
      evidence: evidence.trim() || undefined,
      notes: notes.trim() || undefined,
      expires_at: expiresAt ? new Date(expiresAt).toISOString() : undefined,
      allow_active_probing: allowActiveProbing,
      max_ports_per_target: parsedMaxPorts,
    });
  };

  const submitPolicy = () => {
    const numeric: Array<[keyof PolicyForm, string]> = [
      ["max_concurrency", policyForm.max_concurrency],
      ["requests_per_second", policyForm.requests_per_second],
      ["timeout_seconds", policyForm.timeout_seconds],
      ["max_targets_per_run", policyForm.max_targets_per_run],
    ];
    for (const [field, value] of numeric) {
      if (!Number.isFinite(Number(value)) || Number(value) <= 0) {
        toast({ title: `Enter a valid ${titleize(field).toLowerCase()}`, variant: "error" });
        return;
      }
    }
    const ports = policyForm.allowed_ports
      .split(/[\s,]+/)
      .map((value) => Number(value))
      .filter((value) => Number.isInteger(value) && value > 0 && value <= 65535);
    policyMutation.mutate({
      max_concurrency: Number(policyForm.max_concurrency),
      requests_per_second: Number(policyForm.requests_per_second),
      timeout_seconds: Number(policyForm.timeout_seconds),
      max_targets_per_run: Number(policyForm.max_targets_per_run),
      allowed_ports: ports,
      respect_robots: policyForm.respect_robots,
      safe_mode: policyForm.safe_mode,
      business_hours_only: policyForm.business_hours_only,
    });
  };

  return (
    <div>
      <PageHeader
        title="Discovery & scan configuration"
        description="Authorized discovery only. Every target must match an approved, unexpired ownership record before a scan request is accepted; the worker re-checks each target before probing."
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

      {tab === "new" ? (
        <div className="grid gap-4 xl:grid-cols-3">
          <Card className="xl:col-span-2">
            <CardHeader>
              <CardTitle>Discovery capabilities</CardTitle>
            </CardHeader>
            <CardContent>
              {capabilitiesQuery.isLoading ? (
                <div className="grid gap-2 sm:grid-cols-2">
                  <Skeleton className="h-24" />
                  <Skeleton className="h-24" />
                  <Skeleton className="h-24" />
                  <Skeleton className="h-24" />
                </div>
              ) : capabilitiesQuery.isError ? (
                <ErrorState
                  title="Could not load scan capabilities"
                  message={errorMessage(capabilitiesQuery.error)}
                  onRetry={() => void capabilitiesQuery.refetch()}
                />
              ) : (
                <div className="grid gap-2 sm:grid-cols-2">
                  {capabilities.map((capability) => {
                    const isSelected = capability.scan_type === scanType;
                    return (
                      <button
                        key={capability.scan_type}
                        type="button"
                        disabled={!capability.implemented}
                        onClick={() => setScanType(capability.scan_type)}
                        className={cn(
                          "flex flex-col gap-1.5 rounded-md border p-3 text-left transition-colors",
                          isSelected
                            ? "border-brand-500/60 bg-brand-500/[0.07]"
                            : "border-border bg-surface-raised/40 hover:border-border hover:bg-surface-raised",
                          !capability.implemented && "cursor-not-allowed opacity-60",
                        )}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <p className="text-sm font-medium text-slate-200">{capability.label}</p>
                          <Badge tone={capability.implemented ? "low" : "neutral"}>
                            {capability.implemented ? "Implemented" : "Not implemented"}
                          </Badge>
                        </div>
                        <p className="text-[11px] text-slate-500">{capability.description}</p>
                        <div className="flex flex-wrap items-center gap-1.5">
                          {capability.intrusive ? <Badge tone="medium">Active probe</Badge> : <Badge tone="low">Passive</Badge>}
                          {capability.required_authorization ? <Badge tone="neutral">Authorization required</Badge> : null}
                        </div>
                        {capability.availability_note ? (
                          <p className="text-[11px] text-slate-500">{capability.availability_note}</p>
                        ) : null}
                      </button>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Request a scan</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <label htmlFor="scan-targets" className="mb-1 block text-xs font-medium text-slate-300">
                  Targets (one per line)
                </label>
                <textarea
                  id="scan-targets"
                  value={targetsText}
                  onChange={(event) => setTargetsText(event.target.value)}
                  rows={4}
                  placeholder={"example.com\napp.example.com\n203.0.113.10"}
                  className="w-full rounded-md border border-border bg-surface px-3 py-2 text-xs text-slate-200 placeholder:text-slate-600 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                />
                <p className="mt-1 text-[11px] text-slate-500">
                  Domains, URLs, IP addresses or CIDR ranges up to /26. Each target is checked against approved authorizations.
                </p>
              </div>

              <Input
                label="Run name (optional)"
                value={scanName}
                onChange={(event) => setScanName(event.target.value)}
                placeholder="Quarterly external discovery"
                maxLength={200}
              />

              <Select
                label="Authorization record"
                value={authorizationId}
                onChange={(event) => setAuthorizationId(event.target.value)}
                hint={
                  liveAuthorizations.length === 0
                    ? "No approved, unexpired authorization exists yet. Add one on the Authorizations tab."
                    : "Auto-select picks any live record that covers each target."
                }
              >
                <option value="">Auto-select matching record</option>
                {liveAuthorizations.map((authorization) => (
                  <option key={authorization.id} value={authorization.id}>
                    {authorization.value} · {titleize(authorization.scope_type)}
                    {authorization.allow_active_probing ? " · active allowed" : " · passive only"}
                  </option>
                ))}
              </Select>

              <Checkbox
                label="Include subdomains"
                checked={includeSubdomains}
                onChange={(event) => setIncludeSubdomains(event.target.checked)}
              />

              {(scanType === "port_exposure" || scanType === "full_recon") ? (
                <Input
                  label="Ports to check (optional)"
                  value={portsText}
                  onChange={(event) => setPortsText(event.target.value)}
                  placeholder={`Allowed: ${(policy?.allowed_ports ?? []).join(", ") || "see policy"}`}
                  hint={
                    policy?.safe_mode
                      ? "Safe mode is on for this company; port checks will be refused by the backend."
                      : "Only ports in the company's allowed list are accepted."
                  }
                />
              ) : null}

              <Checkbox
                label="I confirm these targets are owned by this company or explicitly authorised for assessment."
                checked={confirmAuthorized}
                onChange={(event) => setConfirmAuthorized(event.target.checked)}
              />

              <Button
                onClick={submitScan}
                loading={requestMutation.isPending}
                disabled={!can("discovery:run") || !selectedCapability?.implemented}
                className="w-full"
              >
                <Radar aria-hidden="true" className="h-4 w-4" />
                Queue scan
              </Button>
              {!can("discovery:run") ? (
                <p className="text-[11px] text-slate-500">Your role can view scans but not request them.</p>
              ) : null}
            </CardContent>
          </Card>

          <Card className="xl:col-span-3">
            <CardContent className="grid gap-3 text-xs text-slate-400 sm:grid-cols-3">
              <p className="flex gap-2">
                <ShieldCheck aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-400" />
                Scans run only against approved, unexpired scopes. A refused request creates no scan artefact.
              </p>
              <p className="flex gap-2">
                <Ban aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0 text-medium" />
                Port checks are TCP connect only — no payloads and no version probing. Safe mode suppresses them entirely.
              </p>
              <p className="flex gap-2">
                <Radar aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0 text-brand-400" />
                Cloud inventory is not implemented and is rejected rather than simulated.
              </p>
            </CardContent>
          </Card>
        </div>
      ) : null}

      {tab === "history" ? (
        <Card>
          <CardContent className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <Select
                aria-label="Status"
                value={statusFilter}
                onChange={(event) => {
                  setStatusFilter(event.target.value);
                  setPage(1);
                }}
                className="w-44"
              >
                <option value="">All statuses</option>
                {(enums?.scan_statuses ?? []).map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </Select>
              <Select
                aria-label="Scan type"
                value={typeFilter}
                onChange={(event) => {
                  setTypeFilter(event.target.value);
                  setPage(1);
                }}
                className="w-52"
              >
                <option value="">All scan types</option>
                {(enums?.scan_types ?? []).map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </Select>
              {(statusFilter || typeFilter) ? (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setStatusFilter("");
                    setTypeFilter("");
                    setPage(1);
                  }}
                >
                  <RotateCcw aria-hidden="true" className="h-3.5 w-3.5" />
                  Reset
                </Button>
              ) : null}
            </div>

            {scansQuery.isLoading ? (
              <TableLoading columns={7} />
            ) : scansQuery.isError ? (
              <ErrorState
                title="Could not load scans"
                message={errorMessage(scansQuery.error)}
                onRetry={() => void scansQuery.refetch()}
              />
            ) : (scansQuery.data?.items.length ?? 0) === 0 ? (
              <EmptyState
                icon={Radar}
                title="No scan runs yet"
                description="Request an authorized scan on the New scan tab. Completed runs appear here with live result counts."
              />
            ) : (
              <>
                <div className="overflow-x-auto rounded-md border border-border">
                  <Table>
                    <THead>
                      <Tr>
                        <Th>Run</Th>
                        <Th>Type</Th>
                        <Th>Status</Th>
                        <Th>Progress</Th>
                        <Th className="hidden lg:table-cell">Targets</Th>
                        <Th className="hidden xl:table-cell">Results</Th>
                        <Th>Requested</Th>
                      </Tr>
                    </THead>
                    <TBody>
                      {scansQuery.data?.items.map((scan) => (
                        <Tr key={scan.id} className="cursor-pointer" onClick={() => openScan(scan.id)}>
                          <Td>
                            <p className="max-w-[16rem] truncate text-xs font-medium text-slate-200">
                              {scan.name ?? titleize(scan.scan_type)}
                            </p>
                            <p className="text-[11px] text-slate-500">
                              {scan.requested_by_email ?? "system"}
                              {!scan.produced_live_data ? " · no live data" : ""}
                            </p>
                          </Td>
                          <Td><span className="text-xs text-slate-400">{titleize(scan.scan_type)}</span></Td>
                          <Td><StatusBadge status={scan.status} /></Td>
                          <Td>
                            <div className="flex items-center gap-2">
                              <div className="h-1.5 w-16 overflow-hidden rounded-full bg-surface-raised">
                                <div className="h-full rounded-full bg-brand-500" style={{ width: `${scan.progress_percent}%` }} />
                              </div>
                              <span className="num text-[11px] text-slate-400">{scan.progress_percent}%</span>
                            </div>
                          </Td>
                          <Td className="hidden lg:table-cell">
                            <span className="num text-xs text-slate-400">{scan.targets_completed}/{scan.targets_total}</span>
                          </Td>
                          <Td className="hidden xl:table-cell">
                            <span className="text-[11px] text-slate-400">
                              {formatNumber(scan.assets_new)} new assets · {formatNumber(scan.findings_created)} findings
                            </span>
                          </Td>
                          <Td>
                            <span className="text-xs text-slate-400" title={formatDateTime(scan.created_at)}>
                              {relativeTime(scan.created_at)}
                            </span>
                          </Td>
                        </Tr>
                      ))}
                    </TBody>
                  </Table>
                </div>
                <Pagination
                  page={scansQuery.data?.page ?? page}
                  total={scansQuery.data?.total}
                  pageSize={scansQuery.data?.page_size ?? pageSize}
                  onPageChange={setPage}
                />
              </>
            )}
          </CardContent>
        </Card>
      ) : null}

      {tab === "authorizations" ? (
        <div className="grid gap-4 xl:grid-cols-3">
          <Card className="xl:col-span-2">
            <CardHeader>
              <CardTitle>Ownership authorizations</CardTitle>
            </CardHeader>
            <CardContent>
              {authorizationsQuery.isLoading ? (
                <TableLoading columns={5} rows={4} />
              ) : authorizationsQuery.isError ? (
                <ErrorState
                  title="Could not load authorizations"
                  message={errorMessage(authorizationsQuery.error)}
                  onRetry={() => void authorizationsQuery.refetch()}
                />
              ) : (authorizationsQuery.data?.length ?? 0) === 0 ? (
                <EmptyState
                  icon={ClipboardCheck}
                  title="No authorization records"
                  description="Add the domain, IP or CIDR ranges this company owns and can be assessed. A scan cannot run without an approved record."
                />
              ) : (
                <div className="overflow-x-auto rounded-md border border-border">
                  <Table>
                    <THead>
                      <Tr>
                        <Th>Scope</Th>
                        <Th>Status</Th>
                        <Th>Probing</Th>
                        <Th className="hidden lg:table-cell">Expires</Th>
                        <Th className="hidden xl:table-cell">Evidence</Th>
                        <Th>Decision</Th>
                      </Tr>
                    </THead>
                    <TBody>
                      {(authorizationsQuery.data ?? []).map((authorization) => (
                        <Tr key={authorization.id}>
                          <Td>
                            <p className="text-xs font-medium text-slate-200">{authorization.value}</p>
                            <p className="text-[11px] text-slate-500">
                              {titleize(authorization.scope_type)}
                              {authorization.method ? ` · ${titleize(authorization.method)}` : ""}
                            </p>
                          </Td>
                          <Td>
                            <StatusBadge status={authorization.status} />
                            {authorization.is_live ? <Badge tone="low" className="ml-1">Live</Badge> : null}
                          </Td>
                          <Td>
                            {authorization.allow_active_probing ? (
                              <Badge tone="medium">Active allowed</Badge>
                            ) : (
                              <Badge tone="neutral">Passive only</Badge>
                            )}
                          </Td>
                          <Td className="hidden lg:table-cell">
                            <span className="text-xs text-slate-400">
                              {authorization.expires_at ? formatDateTime(authorization.expires_at) : "No expiry"}
                            </span>
                          </Td>
                          <Td className="hidden xl:table-cell">
                            <span className="max-w-[12rem] truncate text-[11px] text-slate-500" title={authorization.evidence ?? ""}>
                              {authorization.evidence ?? "—"}
                            </span>
                          </Td>
                          <Td>
                            {authorization.status === "pending" && can("authorization:approve") ? (
                              <div className="flex gap-1">
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  onClick={() => decisionMutation.mutate({ id: authorization.id, decision: "approved" })}
                                  disabled={decisionMutation.isPending}
                                >
                                  <Check aria-hidden="true" className="h-3.5 w-3.5" /> Approve
                                </Button>
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  onClick={() => decisionMutation.mutate({ id: authorization.id, decision: "rejected" })}
                                  disabled={decisionMutation.isPending}
                                >
                                  <X aria-hidden="true" className="h-3.5 w-3.5" /> Reject
                                </Button>
                              </div>
                            ) : authorization.status === "pending" ? (
                              <span className="text-[11px] text-slate-500">Awaiting approver</span>
                            ) : (
                              <span className="text-[11px] text-slate-500">
                                {authorization.verified_at ? formatDateTime(authorization.verified_at) : "—"}
                              </span>
                            )}
                          </Td>
                        </Tr>
                      ))}
                    </TBody>
                  </Table>
                </div>
              )}
              <p className="mt-3 text-[11px] text-slate-500">
                Four-eyes rule: a company administrator cannot approve an authorization they requested themselves.
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Add authorization</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <Select label="Scope type" value={scopeType} onChange={(event) => setScopeType(event.target.value)}>
                {SCOPE_TYPES.map((value) => (
                  <option key={value} value={value}>{titleize(value)}</option>
                ))}
              </Select>
              <Input
                label="Scope value"
                value={scopeValue}
                onChange={(event) => setScopeValue(event.target.value)}
                placeholder={scopeType === "cidr" ? "203.0.113.0/24" : scopeType.startsWith("ipv") ? "203.0.113.10" : "example.com"}
              />
              <Select label="Verification method" value={method} onChange={(event) => setMethod(event.target.value)}>
                {VERIFICATION_METHODS.map((value) => (
                  <option key={value} value={value}>{titleize(value)}</option>
                ))}
              </Select>
              <Input
                label="Evidence reference"
                value={evidence}
                onChange={(event) => setEvidence(event.target.value)}
                placeholder="Link to signed scope document or DNS TXT record"
                maxLength={4000}
              />
              <Input
                label="Expires at (optional)"
                type="datetime-local"
                value={expiresAt}
                onChange={(event) => setExpiresAt(event.target.value)}
              />
              <Input
                label="Max ports per target"
                type="number"
                min={1}
                max={1000}
                value={maxPorts}
                onChange={(event) => setMaxPorts(event.target.value)}
              />
              <Checkbox
                label="Allow active probing"
                description="Required for TLS, HTTP fingerprint and port checks. Leave off for passive DNS/CT only."
                checked={allowActiveProbing}
                onChange={(event) => setAllowActiveProbing(event.target.checked)}
              />
              <div>
                <label htmlFor="scope-notes" className="mb-1 block text-xs font-medium text-slate-300">Notes</label>
                <textarea
                  id="scope-notes"
                  value={notes}
                  onChange={(event) => setNotes(event.target.value)}
                  rows={2}
                  maxLength={2000}
                  className="w-full rounded-md border border-border bg-surface px-3 py-2 text-xs text-slate-200 placeholder:text-slate-600 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                />
              </div>
              <Button
                className="w-full"
                onClick={submitAuthorization}
                loading={authorizationMutation.isPending}
                disabled={!can("company:write")}
              >
                Request authorization
              </Button>
              <p className="text-[11px] text-slate-500">
                New records start pending. Another administrator with approval permission must approve them before they can authorise scans.
              </p>
            </CardContent>
          </Card>
        </div>
      ) : null}

      {tab === "policy" ? (
        <div className="grid gap-4 xl:grid-cols-3">
          <Card className="xl:col-span-2">
            <CardHeader>
              <CardTitle>Scan policy</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {policyQuery.isLoading ? (
                <div className="grid gap-3 sm:grid-cols-2">
                  <Skeleton className="h-16" />
                  <Skeleton className="h-16" />
                  <Skeleton className="h-16" />
                  <Skeleton className="h-16" />
                </div>
              ) : policyQuery.isError ? (
                <ErrorState
                  title="Could not load scan policy"
                  message={errorMessage(policyQuery.error)}
                  onRetry={() => void policyQuery.refetch()}
                />
              ) : (
                <>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Input
                      label="Max concurrency"
                      type="number"
                      min={1}
                      max={32}
                      value={policyForm.max_concurrency}
                      onChange={(event) => setPolicyForm((current) => ({ ...current, max_concurrency: event.target.value }))}
                      disabled={!can("settings:write")}
                    />
                    <Input
                      label="Requests per second"
                      type="number"
                      min={0.1}
                      step={0.1}
                      max={50}
                      value={policyForm.requests_per_second}
                      onChange={(event) => setPolicyForm((current) => ({ ...current, requests_per_second: event.target.value }))}
                      disabled={!can("settings:write")}
                    />
                    <Input
                      label="Timeout (seconds)"
                      type="number"
                      min={30}
                      max={3600}
                      value={policyForm.timeout_seconds}
                      onChange={(event) => setPolicyForm((current) => ({ ...current, timeout_seconds: event.target.value }))}
                      disabled={!can("settings:write")}
                    />
                    <Input
                      label="Max targets per run"
                      type="number"
                      min={1}
                      max={1000}
                      value={policyForm.max_targets_per_run}
                      onChange={(event) => setPolicyForm((current) => ({ ...current, max_targets_per_run: event.target.value }))}
                      disabled={!can("settings:write")}
                    />
                  </div>
                  <Input
                    label="Allowed ports"
                    value={policyForm.allowed_ports}
                    onChange={(event) => setPolicyForm((current) => ({ ...current, allowed_ports: event.target.value }))}
                    hint="Comma-separated TCP ports. Port scans are restricted to this list."
                    disabled={!can("settings:write")}
                  />
                  <div className="space-y-2">
                    <Checkbox
                      label="Respect robots.txt"
                      checked={policyForm.respect_robots}
                      onChange={(event) => setPolicyForm((current) => ({ ...current, respect_robots: event.target.checked }))}
                      disabled={!can("settings:write")}
                    />
                    <Checkbox
                      label="Safe mode"
                      description="Suppresses TCP port checks. TLS and HTTP probes still require an authorization that allows active probing."
                      checked={policyForm.safe_mode}
                      onChange={(event) => setPolicyForm((current) => ({ ...current, safe_mode: event.target.checked }))}
                      disabled={!can("settings:write")}
                    />
                    <Checkbox
                      label="Business hours only"
                      description="Scheduling window preference recorded in the policy snapshot."
                      checked={policyForm.business_hours_only}
                      onChange={(event) => setPolicyForm((current) => ({ ...current, business_hours_only: event.target.checked }))}
                      disabled={!can("settings:write")}
                    />
                  </div>
                  <Button
                    onClick={submitPolicy}
                    loading={policyMutation.isPending}
                    disabled={!can("settings:write")}
                  >
                    Save scan policy
                  </Button>
                  {!can("settings:write") ? (
                    <p className="text-[11px] text-slate-500">
                      Your role can view the policy but not change it.
                    </p>
                  ) : null}
                </>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Effective constraints</CardTitle></CardHeader>
            <CardContent className="space-y-2 text-xs text-slate-400">
              <p>Policies are snapshotted onto every scan, so later changes do not rewrite the terms of a past run.</p>
              <p className="flex items-center gap-2">
                <SeverityBadge severity="informational" />
                <span>{policy?.safe_mode ? "Port checks currently suppressed" : "Port checks permitted by policy"}</span>
              </p>
              <p className="text-[11px] text-slate-500">
                Global discovery can also be disabled by the platform operator. In that case scan requests are rejected regardless of tenant policy.
              </p>
            </CardContent>
          </Card>
        </div>
      ) : null}

      <ScanDetailModal
        scan={scanDetailQuery.data ?? null}
        loading={scanDetailQuery.isLoading}
        error={scanDetailQuery.isError ? errorMessage(scanDetailQuery.error) : null}
        onClose={closeScan}
        canCancel={can("discovery:run")}
        cancelling={cancelMutation.isPending}
        onCancel={() => selectedScanId && cancelMutation.mutate(selectedScanId)}
        onRetry={() => void scanDetailQuery.refetch()}
      />
    </div>
  );
}

function ScanDetailModal({
  scan,
  loading,
  error,
  onClose,
  canCancel,
  cancelling,
  onCancel,
  onRetry,
}: {
  scan: ScanDetail | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
  canCancel: boolean;
  cancelling: boolean;
  onCancel: () => void;
  onRetry: () => void;
}) {
  const open = loading || Boolean(scan) || Boolean(error);
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={scan?.name ?? "Scan run"}
      description={scan ? `${titleize(scan.scan_type)} · requested ${relativeTime(scan.created_at)}` : undefined}
      size="xl"
      footer={
        <>
          <Button variant="ghost" size="sm" onClick={onClose}>Close</Button>
          {scan && ACTIVE_STATUSES.includes(scan.status) && canCancel ? (
            <Button variant="danger" size="sm" onClick={onCancel} loading={cancelling}>
              <Ban aria-hidden="true" className="h-4 w-4" />
              Cancel scan
            </Button>
          ) : null}
        </>
      }
    >
      {loading ? (
        <div className="flex justify-center py-10"><Spinner className="h-5 w-5 text-brand-400" /></div>
      ) : error ? (
        <ErrorState title="Could not load scan" message={error} onRetry={onRetry} />
      ) : scan ? (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={scan.status} />
            <Badge tone="neutral">{titleize(scan.trigger)}</Badge>
            <Badge tone={scan.produced_live_data ? "low" : "medium"}>
              {scan.produced_live_data ? "Observed live" : "No live observations"}
            </Badge>
            {scan.duration_seconds !== null ? (
              <Badge tone="neutral">{scan.duration_seconds}s</Badge>
            ) : null}
          </div>

          <div>
            <div className="mb-1 flex items-center justify-between text-[11px] text-slate-500">
              <span>Progress</span>
              <span className="num">{scan.progress_percent}% · {scan.targets_completed}/{scan.targets_total} targets</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-surface-raised">
              <div className="h-full rounded-full bg-brand-500" style={{ width: `${scan.progress_percent}%` }} />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {[
              ["Assets discovered", scan.assets_discovered],
              ["New assets", scan.assets_new],
              ["Changed assets", scan.assets_changed],
              ["Removed assets", scan.assets_removed],
              ["Services found", scan.services_found],
              ["Certificates", scan.certificates_found],
              ["Findings created", scan.findings_created],
              ["Changes detected", scan.changes_detected],
            ].map(([label, value]) => (
              <div key={String(label)} className="rounded-md bg-surface-raised/60 px-2 py-1.5">
                <p className="text-[10px] uppercase tracking-wide text-slate-500">{label}</p>
                <p className="num text-sm text-slate-200">{formatNumber(Number(value))}</p>
              </div>
            ))}
          </div>

          {scan.error_message ? (
            <div className="rounded-md border border-critical/40 bg-critical/10 px-3 py-2 text-xs text-critical">
              {scan.error_message}
            </div>
          ) : null}

          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <p className="mb-1 text-[11px] uppercase tracking-wide text-slate-500">Targets</p>
              <div className="flex flex-wrap gap-1">
                {scan.targets.map((target) => (
                  <Badge key={target} tone="neutral">{target}</Badge>
                ))}
              </div>
            </div>
            <div>
              <p className="mb-1 text-[11px] uppercase tracking-wide text-slate-500">Policy snapshot</p>
              <pre className="max-h-28 overflow-auto whitespace-pre-wrap rounded-md bg-surface-raised px-2 py-1.5 text-[10px] text-slate-400">
                {JSON.stringify(scan.policy_snapshot, null, 2)}
              </pre>
            </div>
          </div>

          <div>
            <p className="mb-1 text-[11px] uppercase tracking-wide text-slate-500">Event log</p>
            {scan.events.length === 0 ? (
              <p className="text-xs text-slate-500">No events recorded for this run.</p>
            ) : (
              <ul className="max-h-72 space-y-1.5 overflow-y-auto rounded-md border border-border p-2">
                {scan.events.map((event) => (
                  <li key={event.id} className="flex gap-2 text-[11px]">
                    <span
                      className={cn(
                        "mt-1 h-1.5 w-1.5 shrink-0 rounded-full",
                        event.level === "error" || event.level === "warning"
                          ? "bg-high"
                          : event.level === "success"
                            ? "bg-emerald-400"
                            : "bg-slate-500",
                      )}
                    />
                    <div className="min-w-0">
                      <p className="text-slate-300">
                        {event.stage ? <span className="text-slate-500">[{event.stage}] </span> : null}
                        {event.message}
                      </p>
                      <p className="text-[10px] text-slate-600">{formatDateTime(event.occurred_at)}</p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      ) : null}
    </Modal>
  );
}

export default ScansPage;
