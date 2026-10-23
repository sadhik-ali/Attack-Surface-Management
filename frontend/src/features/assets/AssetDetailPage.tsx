import type { ReactNode } from "react";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  Activity,
  Boxes,
  Cloud,
  ExternalLink,
  FileText,
  Globe2,
  History,
  Pencil,
  ScanLine,
  Server,
  ShieldAlert,
  ShieldCheck,
  ShieldOff,
  Tag,
} from "lucide-react";

import { PageHeader } from "@/components/common/PageHeader";
import {
  CvssBadge,
  FlagBadge,
  HttpStatusBadge,
  RiskBadge,
  SeverityBadge,
  SourceBadge,
  StatusBadge,
} from "@/components/common/Badges";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  ConfirmDialog,
  EmptyState,
  ErrorState,
  Input,
  Modal,
  Select,
  Skeleton,
  Table,
  TBody,
  Td,
  Tabs,
  Th,
  THead,
  Tr,
  useToast,
} from "@/components/ui";
import { apiRequest, errorMessage } from "@/lib/api";
import type { Asset, AssetDetail, AssetEvent, Finding } from "@/lib/apiTypes";
import { titleize } from "@/lib/labels";
import { formatDate, formatDateTime, formatNumber, relativeTime } from "@/lib/utils";
import { useAuth } from "@/context/AuthProvider";

const TABS = [
  { value: "overview", label: "Overview" },
  { value: "services", label: "Services" },
  { value: "certificates", label: "Certificates" },
  { value: "findings", label: "Findings" },
  { value: "timeline", label: "Timeline" },
];

const CRITICALITIES = ["business_critical", "high", "medium", "low", "unknown"];
const EXPOSURES = ["internet_facing", "partner_facing", "internal", "unknown"];
const STATUSES = ["new", "active", "changed", "retired"];

type EditForm = {
  criticality: string;
  exposure: string;
  status: string;
  owner: string;
  technical_contact: string;
  environment: string;
  description: string;
  tags: string;
};

function DetailRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 border-b border-border/60 py-2 last:border-0 sm:flex-row sm:items-baseline sm:justify-between sm:gap-4">
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="min-w-0 text-right text-xs text-slate-300 sm:max-w-[70%]">{children}</dd>
    </div>
  );
}

function EventIcon({ event }: { event: AssetEvent }) {
  const iconClass = "h-3.5 w-3.5";
  if (event.event_type.includes("retire")) return <ShieldOff aria-hidden="true" className={iconClass} />;
  if (event.event_type.includes("finding")) return <ShieldAlert aria-hidden="true" className={iconClass} />;
  if (event.event_type.includes("service")) return <Server aria-hidden="true" className={iconClass} />;
  if (event.event_type.includes("certificate")) return <ShieldCheck aria-hidden="true" className={iconClass} />;
  return <Activity aria-hidden="true" className={iconClass} />;
}

export function AssetDetailPage() {
  const { assetId = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const { selectedCompanyId, can } = useAuth();
  const [tab, setTab] = useState("overview");
  const [editOpen, setEditOpen] = useState(false);
  const [retireOpen, setRetireOpen] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<EditForm | null>(null);

  const assetQuery = useQuery({
    queryKey: ["asset", selectedCompanyId, assetId],
    queryFn: () => apiRequest<AssetDetail>(`/companies/${selectedCompanyId}/assets/${assetId}`),
    enabled: Boolean(selectedCompanyId && assetId),
  });

  const findingsQuery = useQuery({
    queryKey: ["asset-findings", selectedCompanyId, assetId],
    queryFn: () => apiRequest<Finding[]>(`/companies/${selectedCompanyId}/assets/${assetId}/findings`),
    enabled: Boolean(selectedCompanyId && assetId && tab === "findings"),
  });

  const timelineQuery = useQuery({
    queryKey: ["asset-timeline", selectedCompanyId, assetId],
    queryFn: () => apiRequest<AssetEvent[]>(`/companies/${selectedCompanyId}/assets/${assetId}/timeline`, { params: { limit: 200 } }),
    enabled: Boolean(selectedCompanyId && assetId),
  });

  const updateMutation = useMutation({
    mutationFn: (form: EditForm) =>
      apiRequest<Asset>(`/companies/${selectedCompanyId}/assets/${assetId}`, {
        method: "PATCH",
        body: {
          criticality: form.criticality,
          exposure: form.exposure,
          status: form.status,
          owner: form.owner.trim(),
          technical_contact: form.technical_contact.trim(),
          environment: form.environment.trim(),
          description: form.description.trim(),
          tags: form.tags.split(",").map((tag) => tag.trim()).filter(Boolean),
        },
      }),
    onSuccess: async () => {
      toast({ title: "Asset updated", variant: "success" });
      setEditOpen(false);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["asset", selectedCompanyId, assetId] }),
        queryClient.invalidateQueries({ queryKey: ["assets"] }),
        queryClient.invalidateQueries({ queryKey: ["asset-timeline", selectedCompanyId, assetId] }),
      ]);
    },
    onError: (error) => setEditError(errorMessage(error)),
  });

  const retireMutation = useMutation({
    mutationFn: () =>
      apiRequest<{ message: string }>(`/companies/${selectedCompanyId}/assets/${assetId}`, { method: "DELETE" }),
    onSuccess: async () => {
      toast({ title: "Asset retired", description: "History is retained for audit.", variant: "success" });
      setRetireOpen(false);
      await queryClient.invalidateQueries({ queryKey: ["assets"] });
      navigate("/assets");
    },
    onError: (error) => toast({ title: "Could not retire asset", description: errorMessage(error), variant: "error" }),
  });

  if (assetQuery.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <div className="grid gap-4 lg:grid-cols-3">
          <Skeleton className="h-64 lg:col-span-2" />
          <Skeleton className="h-64" />
        </div>
      </div>
    );
  }
  if (assetQuery.isError) {
    return (
      <ErrorState
        title="Asset unavailable"
        message={errorMessage(assetQuery.error)}
        onRetry={() => void assetQuery.refetch()}
      />
    );
  }
  const asset = assetQuery.data;
  if (!asset) return null;

  const openEdit = () => {
    setEditForm({
      criticality: asset.criticality,
      exposure: asset.exposure,
      status: asset.status,
      owner: asset.owner ?? "",
      technical_contact: asset.technical_contact ?? "",
      environment: asset.environment ?? "",
      description: asset.description ?? "",
      tags: asset.tags.join(", "),
    });
    setEditError(null);
    setEditOpen(true);
  };

  const domain = asset.domain;
  const ip = asset.ip;
  const api = asset.api;
  const cloud = asset.cloud;
  const events = timelineQuery.data ?? asset.events;

  return (
    <div>
      <PageHeader
        backTo="/assets"
        backLabel="Asset inventory"
        title={asset.name}
        description={
          <span className="flex flex-wrap items-center gap-2">
            <span>{titleize(asset.asset_type)}</span>
            <span aria-hidden="true">·</span>
            <StatusBadge status={asset.status} />
            <RiskBadge score={asset.risk_score} classification={asset.risk_classification} />
            <SourceBadge source={asset.source} provenance={asset.provenance} />
          </span>
        }
        actions={
          <>
            {can("discovery:run") ? (
              <Link to={`/scans?target=${encodeURIComponent(asset.name)}`}>
                <Button variant="ghost" size="sm">
                  <ScanLine aria-hidden="true" className="h-4 w-4" />
                  Scan target
                </Button>
              </Link>
            ) : null}
            {can("asset:write") ? (
              <Button variant="ghost" size="sm" onClick={openEdit}>
                <Pencil aria-hidden="true" className="h-4 w-4" />
                Edit
              </Button>
            ) : null}
            {can("asset:delete") && asset.status !== "retired" ? (
              <Button variant="ghost" size="sm" className="text-critical hover:text-critical" onClick={() => setRetireOpen(true)}>
                <ShieldOff aria-hidden="true" className="h-4 w-4" />
                Retire
              </Button>
            ) : null}
          </>
        }
      />

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Inventory record</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid gap-x-8 sm:grid-cols-2">
              <DetailRow label="Asset type">{titleize(asset.asset_type)}</DetailRow>
              <DetailRow label="Criticality">{titleize(asset.criticality)}</DetailRow>
              <DetailRow label="Exposure">{titleize(asset.exposure)}</DetailRow>
              <DetailRow label="Environment">{asset.environment ? titleize(asset.environment) : "—"}</DetailRow>
              <DetailRow label="Owner">{asset.owner ?? "Unassigned"}</DetailRow>
              <DetailRow label="Technical contact">{asset.technical_contact ?? "—"}</DetailRow>
              <DetailRow label="First seen">{asset.first_seen ? formatDateTime(asset.first_seen) : "Not observed"}</DetailRow>
              <DetailRow label="Last seen">{asset.last_seen ? formatDateTime(asset.last_seen) : "Not observed"}</DetailRow>
              <DetailRow label="Last changed">{asset.last_changed_at ? relativeTime(asset.last_changed_at) : "No recorded change"}</DetailRow>
              <DetailRow label="Configuration changes">{formatNumber(asset.change_count)}</DetailRow>
              <DetailRow label="Open findings">
                {asset.open_findings} total · {asset.critical_findings} critical · {asset.high_findings} high
              </DetailRow>
              <DetailRow label="Services">{formatNumber(asset.services.length)} observed</DetailRow>
            </dl>
            {asset.description ? (
              <p className="mt-4 rounded-md bg-surface-raised/60 px-3 py-2.5 text-xs leading-relaxed text-slate-400">
                {asset.description}
              </p>
            ) : null}
            {asset.tags.length > 0 ? (
              <div className="mt-3 flex flex-wrap items-center gap-1.5">
                <Tag aria-hidden="true" className="h-3.5 w-3.5 text-slate-500" />
                {asset.tags.map((tag) => (
                  <Badge key={tag} tone="neutral">{tag}</Badge>
                ))}
              </div>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Risk summary</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-baseline justify-between">
              <span className="text-xs text-slate-500">Explainable score</span>
              <span className="num text-3xl font-semibold text-slate-50">{asset.risk_score.toFixed(1)}</span>
            </div>
            <RiskBadge score={asset.risk_score} classification={asset.risk_classification} />
            <div className="space-y-2">
              {(["critical", "high", "medium", "low", "info"] as const).map((severity) => {
                const count = asset.findings_by_severity[severity] ?? asset.findings_by_severity[severity === "info" ? "informational" : severity] ?? 0;
                if (count === 0) return null;
                return (
                  <div key={severity} className="flex items-center justify-between gap-2">
                    <SeverityBadge severity={severity} />
                    <span className="num text-xs text-slate-300">{count}</span>
                  </div>
                );
              })}
              {asset.open_findings === 0 ? <p className="text-xs text-slate-500">No open findings on this asset.</p> : null}
            </div>
            <div className="rounded-md bg-surface-raised/60 px-3 py-2 text-[11px] leading-relaxed text-slate-500">
              Scores combine finding severity, confidence, exposure and business criticality. They are prioritisation
              guidance, not proof of exploitability.
            </div>
          </CardContent>
        </Card>
      </div>

      <Card className="mt-4">
        <CardContent>
          <Tabs
            value={tab}
            onValueChange={setTab}
            items={TABS.map((item) => ({
              value: item.value,
              label: item.label,
              content: null,
            }))}
          />

          <div className="mt-4">
            {tab === "overview" ? (
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <h3 className="mb-2 text-sm font-medium text-slate-200">Identifiers &amp; observations</h3>
                  {domain ? (
                    <dl>
                      <DetailRow label="FQDN">{domain.fqdn}</DetailRow>
                      <DetailRow label="Root domain">{domain.root_domain}</DetailRow>
                      <DetailRow label="Subdomain">{domain.is_subdomain ? (domain.host_label ?? "Yes") : "No"}</DetailRow>
                      <DetailRow label="Wildcard">{domain.is_wildcard ? "Yes" : "No"}</DetailRow>
                      <DetailRow label="Resolves to">
                        {domain.resolves_to.length > 0 ? domain.resolves_to.join(", ") : "Not resolved"}
                      </DetailRow>
                      <DetailRow label="Nameservers">
                        {domain.nameservers.length > 0 ? domain.nameservers.join(", ") : "Not recorded"}
                      </DetailRow>
                      <DetailRow label="Web server">{domain.web_server ?? "—"}</DetailRow>
                      <DetailRow label="HTTP status">
                        <HttpStatusBadge status={domain.http_status} />
                      </DetailRow>
                      <DetailRow label="Page title">{domain.http_title ?? "—"}</DetailRow>
                      <DetailRow label="DNS resolved">{domain.dns_resolved_at ? relativeTime(domain.dns_resolved_at) : "Not resolved"}</DetailRow>
                    </dl>
                  ) : ip ? (
                    <dl>
                      <DetailRow label="Address">{ip.address}</DetailRow>
                      <DetailRow label="Version">{ip.version.toUpperCase()}</DetailRow>
                      <DetailRow label="Private address">{ip.is_private ? "Yes" : "No"}</DetailRow>
                      <DetailRow label="Reverse DNS">{ip.reverse_dns ?? "—"}</DetailRow>
                      <DetailRow label="ASN">{ip.asn ?? "—"}</DetailRow>
                      <DetailRow label="Organisation">{ip.asn_organization ?? "—"}</DetailRow>
                      <DetailRow label="Location">
                        {[ip.geo_city, ip.geo_country_name ?? ip.geo_country].filter(Boolean).join(", ") || "—"}
                      </DetailRow>
                      <DetailRow label="Provider hint">{ip.provider_hint ?? "—"}</DetailRow>
                      <DetailRow label="Elastic cloud IP">{ip.is_cloud_elastic_ip ? "Yes" : "No"}</DetailRow>
                    </dl>
                  ) : api ? (
                    <dl>
                      <DetailRow label="URL"><span className="break-all">{api.url}</span></DetailRow>
                      <DetailRow label="Method">{api.method}</DetailRow>
                      <DetailRow label="Path">{api.path ?? "—"}</DetailRow>
                      <DetailRow label="Format">{api.api_format ? titleize(api.api_format) : "—"}</DetailRow>
                      <DetailRow label="Authentication">{api.auth_type ? titleize(api.auth_type) : api.requires_auth ? "Required" : "None"}</DetailRow>
                      <DetailRow label="Unauthenticated access">
                        <FlagBadge active={api.unauthenticated_access} tone="critical">Unauthenticated</FlagBadge>
                        {!api.unauthenticated_access ? <span className="text-slate-500">Not observed</span> : null}
                      </DetailRow>
                      <DetailRow label="Deprecated"><FlagBadge active={api.is_deprecated} tone="high">Deprecated</FlagBadge></DetailRow>
                      <DetailRow label="Documented">{api.is_documented ? "Yes" : "No"}</DetailRow>
                      <DetailRow label="Last status"><HttpStatusBadge status={api.last_status_code} /></DetailRow>
                      <DetailRow label="Last latency">{api.last_latency_ms !== null ? `${api.last_latency_ms} ms` : "—"}</DetailRow>
                    </dl>
                  ) : cloud ? (
                    <div className="space-y-3">
                      <dl>
                        <DetailRow label="Provider">{titleize(cloud.provider)}</DetailRow>
                        <DetailRow label="Account">{cloud.account_alias ?? cloud.account_id ?? "—"}</DetailRow>
                        <DetailRow label="Resource type">{cloud.resource_type ? titleize(cloud.resource_type) : "—"}</DetailRow>
                        <DetailRow label="External ID">{cloud.external_id}</DetailRow>
                        <DetailRow label="Region">{cloud.region ?? "—"}</DetailRow>
                        <DetailRow label="Public access">
                          <FlagBadge active={cloud.public_access} tone="critical">Publicly accessible</FlagBadge>
                        </DetailRow>
                        <DetailRow label="Public ACL"><FlagBadge active={cloud.public_acl} tone="high">Public ACL</FlagBadge></DetailRow>
                        <DetailRow label="Encryption">{cloud.encrypted ? "Enabled" : "Not reported"}</DetailRow>
                        <DetailRow label="Logging">{cloud.logging_enabled ? "Enabled" : "Not reported"}</DetailRow>
                        <DetailRow label="Observed">{cloud.observed_at ? relativeTime(cloud.observed_at) : "—"}</DetailRow>
                      </dl>
                      <p className="rounded-md border border-medium/30 bg-medium/10 px-3 py-2 text-[11px] leading-relaxed text-medium">
                        Cloud configuration is only as trustworthy as its source. No live cloud provider integration is
                        implemented in this build; rows labelled “Sample data” are demonstration fixtures.
                      </p>
                    </div>
                  ) : (
                    <EmptyState icon={Boxes} title="No type-specific detail" description="This record has no extended identifiers." className="py-8" />
                  )}
                </div>

                <div>
                  <h3 className="mb-2 text-sm font-medium text-slate-200">Services</h3>
                  {asset.services.length === 0 ? (
                    <EmptyState icon={Server} title="No exposed services" description="Port and service checks require an authorized active scan." className="py-8" />
                  ) : (
                    <ul className="space-y-2">
                      {asset.services.slice(0, 6).map((service) => (
                        <li key={service.id} className="flex items-center justify-between gap-3 rounded-md border border-border bg-surface-raised/40 px-3 py-2">
                          <div className="min-w-0">
                            <p className="text-xs font-medium text-slate-200">
                              <span className="num">{service.port}</span>/{service.transport} · {service.service_name ?? "unknown"}
                            </p>
                            <p className="truncate text-[11px] text-slate-500">
                              {[service.product, service.version].filter(Boolean).join(" ") || "No product banner"}
                            </p>
                          </div>
                          <div className="flex shrink-0 items-center gap-1.5">
                            {service.is_risky ? <Badge tone={service.risk_level === "critical" ? "critical" : "high"}>Risky</Badge> : null}
                            {!service.is_encrypted ? <Badge tone="medium">Plaintext</Badge> : null}
                            <Badge tone="neutral">{service.state}</Badge>
                          </div>
                        </li>
                      ))}
                    </ul>
                  )}
                  <h3 className="mb-2 mt-4 text-sm font-medium text-slate-200">Technologies</h3>
                  {domain && domain.technologies.length > 0 ? (
                    <div className="flex flex-wrap gap-1.5">
                      {domain.technologies.map((technology) => (
                        <Badge key={technology} tone="brand">{technology}</Badge>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-slate-500">No fingerprint recorded for this asset.</p>
                  )}
                  {asset.url ? (
                    <a
                      href={asset.url}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="mt-4 inline-flex items-center gap-1 text-xs font-medium text-brand-400 hover:text-brand-300"
                    >
                      Open asset URL <ExternalLink aria-hidden="true" className="h-3 w-3" />
                    </a>
                  ) : null}
                </div>
              </div>
            ) : null}

            {tab === "services" ? (
              asset.services.length === 0 ? (
                <EmptyState
                  icon={Server}
                  title="No exposed services recorded"
                  description="Services only appear after an authorized active scan that is permitted to probe ports."
                  className="py-10"
                />
              ) : (
                <div className="overflow-x-auto rounded-md border border-border">
                  <Table>
                    <THead>
                      <Tr>
                        <Th>Port</Th>
                        <Th>Service</Th>
                        <Th>Product / version</Th>
                        <Th className="hidden md:table-cell">OS</Th>
                        <Th>Flags</Th>
                        <Th className="hidden lg:table-cell">First seen</Th>
                        <Th className="hidden lg:table-cell">Last seen</Th>
                      </Tr>
                    </THead>
                    <TBody>
                      {asset.services.map((service) => (
                        <Tr key={service.id}>
                          <Td><span className="num text-sm text-slate-200">{service.port}</span><span className="text-xs text-slate-500">/{service.transport}</span></Td>
                          <Td>{service.service_name ?? "unknown"}</Td>
                          <Td>
                            <span className="text-xs text-slate-300">{[service.product, service.version].filter(Boolean).join(" ") || "—"}</span>
                            {service.banner ? <p className="max-w-[20rem] truncate text-[11px] text-slate-500" title={service.banner}>{service.banner}</p> : null}
                          </Td>
                          <Td className="hidden md:table-cell"><span className="text-xs text-slate-400">{service.operating_system ?? "—"}</span></Td>
                          <Td>
                            <div className="flex flex-wrap gap-1">
                              {!service.is_expected ? <Badge tone="high">Unexpected</Badge> : null}
                              {!service.is_encrypted ? <Badge tone="medium">Unencrypted</Badge> : null}
                              {service.is_risky ? <Badge tone={service.risk_level === "critical" ? "critical" : "high"}>Risky</Badge> : null}
                              {service.is_expected && service.is_encrypted && !service.is_risky ? <Badge tone="low">Expected</Badge> : null}
                            </div>
                          </Td>
                          <Td className="hidden lg:table-cell"><span className="text-xs text-slate-500">{service.first_seen ? relativeTime(service.first_seen) : "—"}</span></Td>
                          <Td className="hidden lg:table-cell"><span className="text-xs text-slate-500">{service.last_seen ? relativeTime(service.last_seen) : "—"}</span></Td>
                        </Tr>
                      ))}
                    </TBody>
                  </Table>
                </div>
              )
            ) : null}

            {tab === "certificates" ? (
              asset.certificates.length === 0 ? (
                <EmptyState
                  icon={ShieldCheck}
                  title="No certificate observed"
                  description="TLS certificates are recorded when an authorized scan performs a TLS handshake."
                  className="py-10"
                />
              ) : (
                <div className="overflow-x-auto rounded-md border border-border">
                  <Table>
                    <THead>
                      <Tr>
                        <Th>Host</Th>
                        <Th>Subject / issuer</Th>
                        <Th>Expiry</Th>
                        <Th>Status</Th>
                        <Th className="hidden md:table-cell">Hostname</Th>
                      </Tr>
                    </THead>
                    <TBody>
                      {asset.certificates.map((certificate) => (
                        <Tr key={certificate.id}>
                          <Td><span className="text-sm text-slate-200">{certificate.host}</span><span className="text-xs text-slate-500">:{certificate.port}</span></Td>
                          <Td>
                            <p className="text-xs text-slate-300">{certificate.subject_common_name ?? "—"}</p>
                            <p className="text-[11px] text-slate-500">{certificate.issuer_organization ?? certificate.issuer_common_name ?? "Unknown issuer"}</p>
                          </Td>
                          <Td>
                            <p className="text-xs text-slate-300">{certificate.not_after ? formatDate(certificate.not_after) : "—"}</p>
                            <p className="text-[11px] text-slate-500">
                              {certificate.days_remaining === null
                                ? "No expiry data"
                                : certificate.days_remaining < 0
                                  ? `${Math.abs(certificate.days_remaining)} days ago`
                                  : `${certificate.days_remaining} days left`}
                            </p>
                          </Td>
                          <Td><StatusBadge status={certificate.status} /></Td>
                          <Td className="hidden md:table-cell">
                            <Badge tone={certificate.hostname_matches ? "low" : "critical"}>
                              {certificate.hostname_matches ? "Matches" : "Mismatch"}
                            </Badge>
                          </Td>
                        </Tr>
                      ))}
                    </TBody>
                  </Table>
                </div>
              )
            ) : null}

            {tab === "findings" ? (
              findingsQuery.isLoading ? (
                <Skeleton className="h-40" />
              ) : findingsQuery.isError ? (
                <ErrorState title="Could not load findings" message={errorMessage(findingsQuery.error)} onRetry={() => void findingsQuery.refetch()} />
              ) : (findingsQuery.data?.length ?? 0) === 0 ? (
                <EmptyState icon={ShieldCheck} title="No findings on this asset" description="Findings appear after authorized probes or user review." className="py-10" />
              ) : (
                <div className="overflow-x-auto rounded-md border border-border">
                  <Table>
                    <THead>
                      <Tr>
                        <Th>Finding</Th>
                        <Th>Severity</Th>
                        <Th align="right">Risk</Th>
                        <Th className="hidden md:table-cell">CVSS</Th>
                        <Th>Status</Th>
                        <Th className="hidden lg:table-cell">Discovered</Th>
                      </Tr>
                    </THead>
                    <TBody>
                      {findingsQuery.data?.map((finding) => (
                        <Tr key={finding.id}>
                          <Td>
                            <Link to={`/findings?focus=${finding.id}`} className="font-medium text-slate-200 hover:text-brand-400">{finding.title}</Link>
                            <p className="text-[11px] text-slate-500">{titleize(finding.finding_type)} · {finding.confidence} confidence</p>
                          </Td>
                          <Td><SeverityBadge severity={finding.severity} /></Td>
                          <Td align="right"><span className="num text-sm font-medium text-slate-200">{finding.risk_score.toFixed(1)}</span></Td>
                          <Td className="hidden md:table-cell"><CvssBadge score={finding.cvss_base_score} /></Td>
                          <Td><StatusBadge status={finding.status} /></Td>
                          <Td className="hidden lg:table-cell"><span className="text-xs text-slate-500">{relativeTime(finding.discovered_at)}</span></Td>
                        </Tr>
                      ))}
                    </TBody>
                  </Table>
                </div>
              )
            ) : null}

            {tab === "timeline" ? (
              timelineQuery.isError ? (
                <ErrorState title="Could not load timeline" message={errorMessage(timelineQuery.error)} onRetry={() => void timelineQuery.refetch()} />
              ) : events.length === 0 ? (
                <EmptyState icon={History} title="No recorded events" description="Discovery, configuration changes and manual edits are logged here." className="py-10" />
              ) : (
                <ol className="relative ml-2 space-y-4 border-l border-border pl-5">
                  {events.map((event) => (
                    <li key={event.id} className="relative">
                      <span className="absolute -left-[27px] top-0.5 inline-flex h-4 w-4 items-center justify-center rounded-full border border-border bg-surface-raised text-slate-400">
                        <EventIcon event={event} />
                      </span>
                      <div className="flex flex-wrap items-baseline justify-between gap-2">
                        <p className="text-sm text-slate-200">{event.summary}</p>
                        <span className="text-[11px] text-slate-500" title={formatDateTime(event.occurred_at)}>{relativeTime(event.occurred_at)}</span>
                      </div>
                      <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
                        <Badge tone="neutral">{titleize(event.event_type)}</Badge>
                        {event.severity ? <SeverityBadge severity={event.severity} dot={false} /> : null}
                        <span>{titleize(event.source)}</span>
                      </div>
                      {event.detail ? (
                        <p className="mt-1 line-clamp-2 text-[11px] text-slate-500">{JSON.stringify(event.detail)}</p>
                      ) : null}
                    </li>
                  ))}
                </ol>
              )
            ) : null}
          </div>
        </CardContent>
      </Card>

      <div className="mt-4 flex flex-wrap items-center gap-3 text-[11px] text-slate-500">
        <span className="inline-flex items-center gap-1"><Globe2 aria-hidden="true" className="h-3.5 w-3.5" /> Provenance: {asset.provenance?.label ?? titleize(asset.source)}</span>
        <span className="inline-flex items-center gap-1"><Cloud aria-hidden="true" className="h-3.5 w-3.5" /> Cloud inventory is not live unless labelled observed</span>
        <span className="inline-flex items-center gap-1"><FileText aria-hidden="true" className="h-3.5 w-3.5" /> History is retained after retirement</span>
      </div>

      <Modal
        open={editOpen && editForm !== null}
        onClose={() => setEditOpen(false)}
        title="Edit asset context"
        description="Ownership and classification fields. Observed technical facts are not editable here."
        size="lg"
        footer={
          <>
            <Button variant="ghost" size="sm" onClick={() => setEditOpen(false)} disabled={updateMutation.isPending}>Cancel</Button>
            <Button
              size="sm"
              onClick={() => {
                if (!editForm) return;
                setEditError(null);
                updateMutation.mutate(editForm);
              }}
              disabled={updateMutation.isPending}
            >
              {updateMutation.isPending ? "Saving…" : "Save changes"}
            </Button>
          </>
        }
      >
        {editForm ? (
          <form
            className="space-y-4"
            onSubmit={(event) => {
              event.preventDefault();
              setEditError(null);
              updateMutation.mutate(editForm);
            }}
          >
            {editError ? (
              <p role="alert" className="rounded-md border border-critical/30 bg-critical/10 px-3 py-2 text-xs text-critical">{editError}</p>
            ) : null}
            <div className="grid gap-4 sm:grid-cols-2">
              <Select label="Criticality" value={editForm.criticality} onChange={(event) => setEditForm({ ...editForm, criticality: event.target.value })}>
                {CRITICALITIES.map((value) => <option key={value} value={value}>{titleize(value)}</option>)}
              </Select>
              <Select label="Exposure" value={editForm.exposure} onChange={(event) => setEditForm({ ...editForm, exposure: event.target.value })}>
                {EXPOSURES.map((value) => <option key={value} value={value}>{titleize(value)}</option>)}
              </Select>
              <Select label="Status" value={editForm.status} onChange={(event) => setEditForm({ ...editForm, status: event.target.value })}>
                {STATUSES.map((value) => <option key={value} value={value}>{titleize(value)}</option>)}
              </Select>
              <Input label="Environment" value={editForm.environment} onChange={(event) => setEditForm({ ...editForm, environment: event.target.value })} />
              <Input label="Owner" value={editForm.owner} onChange={(event) => setEditForm({ ...editForm, owner: event.target.value })} />
              <Input label="Technical contact" value={editForm.technical_contact} onChange={(event) => setEditForm({ ...editForm, technical_contact: event.target.value })} />
            </div>
            <Input label="Tags" value={editForm.tags} onChange={(event) => setEditForm({ ...editForm, tags: event.target.value })} hint="Comma separated." />
            <Input label="Description" value={editForm.description} onChange={(event) => setEditForm({ ...editForm, description: event.target.value })} />
            <button type="submit" className="hidden" aria-hidden="true" tabIndex={-1} />
          </form>
        ) : null}
      </Modal>

      <ConfirmDialog
        open={retireOpen}
        title="Retire this asset?"
        description="The asset is removed from active inventory but its history, findings and audit trail are retained. Discovery may re-add it if it is still in an authorized scope."
        confirmLabel="Retire asset"
        destructive
        loading={retireMutation.isPending}
        onConfirm={() => retireMutation.mutate()}
        onCancel={() => setRetireOpen(false)}
      />
    </div>
  );
}

export default AssetDetailPage;
