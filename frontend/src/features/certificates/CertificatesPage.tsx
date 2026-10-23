import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { CalendarClock, Info, RotateCcw, ShieldCheck, ShieldQuestion, TriangleAlert } from "lucide-react";

import { PageHeader } from "@/components/common/PageHeader";
import { SourceBadge, StatusBadge } from "@/components/common/Badges";
import { SearchInput, TableLoading } from "@/components/common/TableState";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  EmptyState,
  ErrorState,
  Modal,
  Pagination,
  Select,
  Skeleton,
  Table,
  TBody,
  Td,
  Th,
  THead,
  Tr,
} from "@/components/ui";
import { apiRequest, errorMessage } from "@/lib/api";
import type { Certificate, CertificateHealth, Page } from "@/lib/apiTypes";
import { titleize } from "@/lib/labels";
import { formatDate, formatDateTime, relativeTime } from "@/lib/utils";
import { useAuth } from "@/context/AuthProvider";
import { cn } from "@/lib/utils";

const STATUSES = ["valid", "expiring_soon", "expired", "not_observed"];

function daysLabel(certificate: Certificate): string {
  if (certificate.days_remaining === null) return "No expiry data";
  if (certificate.days_remaining < 0) return `${Math.abs(certificate.days_remaining)} days ago`;
  if (certificate.days_remaining === 0) return "Expires today";
  return `${certificate.days_remaining} days left`;
}

function daysTone(certificate: Certificate): "critical" | "high" | "medium" | "low" | "neutral" {
  if (certificate.is_expired || (certificate.days_remaining !== null && certificate.days_remaining < 0)) return "critical";
  if (certificate.days_remaining !== null && certificate.days_remaining <= 7) return "high";
  if (certificate.days_remaining !== null && certificate.days_remaining <= 30) return "medium";
  if (certificate.days_remaining !== null) return "low";
  return "neutral";
}

function CertificateDetail({ certificateId, onClose }: { certificateId: string | null; onClose: () => void }) {
  const { selectedCompanyId } = useAuth();
  const query = useQuery({
    queryKey: ["certificate", selectedCompanyId, certificateId],
    queryFn: () => apiRequest<Certificate>(`/companies/${selectedCompanyId}/certificates/${certificateId}`),
    enabled: Boolean(selectedCompanyId && certificateId),
  });
  const certificate = query.data;
  return (
    <Modal
      open={Boolean(certificateId)}
      onClose={onClose}
      title={certificate?.host ? `${certificate.host}:${certificate.port}` : "Certificate detail"}
      description="Observed TLS certificate. Fields are recorded from a permitted handshake, not from a certificate authority API."
      size="lg"
    >
      {query.isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-6 w-64" />
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
        </div>
      ) : query.isError ? (
        <ErrorState title="Could not load certificate" message={errorMessage(query.error)} onRetry={() => void query.refetch()} />
      ) : certificate ? (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={certificate.status} />
            <Badge tone={daysTone(certificate)}>{daysLabel(certificate)}</Badge>
            <Badge tone={certificate.hostname_matches ? "low" : "critical"}>
              {certificate.hostname_matches ? "Hostname matches" : "Hostname mismatch"}
            </Badge>
            {certificate.is_self_signed ? <Badge tone="high">Self-signed</Badge> : null}
            {certificate.weak_key ? <Badge tone="high">Weak key</Badge> : null}
            {certificate.deprecated_signature ? <Badge tone="medium">Deprecated signature</Badge> : null}
            {certificate.san_wildcard || certificate.is_wildcard ? <Badge tone="brand">Wildcard SAN</Badge> : null}
          </div>

          <dl className="grid gap-x-6 sm:grid-cols-2">
            {[
              ["Subject CN", certificate.subject_common_name ?? "—"],
              ["Subject organisation", certificate.subject_organization ?? "—"],
              ["Issuer CN", certificate.issuer_common_name ?? "—"],
              ["Issuer organisation", certificate.issuer_organization ?? "—"],
              ["Serial number", certificate.serial_number ?? "—"],
              ["Not before", certificate.not_before ? formatDateTime(certificate.not_before) : "—"],
              ["Not after", certificate.not_after ? formatDateTime(certificate.not_after) : "—"],
              ["Observed at", certificate.observed_at ? formatDateTime(certificate.observed_at) : "—"],
              ["Key", certificate.key_algorithm ? `${certificate.key_algorithm}${certificate.key_size ? ` ${certificate.key_size} bit` : ""}` : "—"],
              ["Signature", certificate.signature_algorithm ?? "—"],
              ["TLS version", certificate.tls_version ?? "—"],
              ["Chain length", certificate.certificate_chain_length !== null ? String(certificate.certificate_chain_length) : "—"],
              ["OCSP", certificate.ocsp_url ?? "—"],
              ["Source", titleize(certificate.source)],
            ].map(([label, value]) => (
              <div key={label} className="border-b border-border/60 py-2">
                <dt className="text-[11px] uppercase tracking-wide text-slate-500">{label}</dt>
                <dd className="mt-0.5 break-words text-xs text-slate-300">{value}</dd>
              </div>
            ))}
          </dl>

          <div>
            <p className="text-xs font-medium text-slate-300">Subject alternative names</p>
            {certificate.subject_alternative_names.length > 0 ? (
              <div className="mt-1.5 flex flex-wrap gap-1">
                {certificate.subject_alternative_names.map((name) => (
                  <Badge key={name} tone="neutral">{name}</Badge>
                ))}
              </div>
            ) : (
              <p className="mt-1 text-xs text-slate-500">No SAN entries recorded.</p>
            )}
          </div>

          {certificate.fingerprint_sha256 ? (
            <div>
              <p className="text-xs font-medium text-slate-300">SHA-256 fingerprint</p>
              <p className="mt-1 break-all rounded bg-surface-raised px-2 py-1.5 font-mono text-[10px] text-slate-400">{certificate.fingerprint_sha256}</p>
            </div>
          ) : null}

          {certificate.error ? (
            <p className="rounded-md border border-critical/30 bg-critical/10 px-3 py-2 text-xs text-critical">{certificate.error}</p>
          ) : null}

          {certificate.asset_id ? (
            <Link to={`/assets/${certificate.asset_id}`} className="inline-block text-xs font-medium text-brand-400 hover:text-brand-300" onClick={onClose}>
              Open linked asset: {certificate.asset_name ?? "asset"}
            </Link>
          ) : null}
        </div>
      ) : null}
    </Modal>
  );
}

export function CertificatesPage() {
  const { selectedCompanyId } = useAuth();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [expiresWithin, setExpiresWithin] = useState("");
  const [mismatch, setMismatch] = useState("");
  const [selfSigned, setSelfSigned] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize] = useState(25);
  const [sort, setSort] = useState("not_after");
  const [order, setOrder] = useState<"asc" | "desc">("asc");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const healthQuery = useQuery({
    queryKey: ["certificate-health", selectedCompanyId],
    queryFn: () => apiRequest<CertificateHealth>(`/companies/${selectedCompanyId}/certificates/health`),
    enabled: Boolean(selectedCompanyId),
  });

  const query = useQuery({
    queryKey: ["certificates", selectedCompanyId, search, status, expiresWithin, mismatch, selfSigned, page, pageSize, sort, order],
    queryFn: () =>
      apiRequest<Page<Certificate>>(`/companies/${selectedCompanyId}/certificates`, {
        params: {
          q: search.trim() || undefined,
          status: status || undefined,
          expires_within_days: expiresWithin ? Number(expiresWithin) : undefined,
          hostname_mismatch: mismatch === "" ? undefined : mismatch === "true",
          self_signed: selfSigned === "" ? undefined : selfSigned === "true",
          page,
          page_size: pageSize,
          sort,
          order,
        },
      }),
    enabled: Boolean(selectedCompanyId),
    placeholderData: (previous) => previous,
  });

  const health = healthQuery.data;
  const data = query.data;
  const items = data?.items ?? [];
  const maxBucket = Math.max(1, ...(health?.expiry_buckets.map((bucket) => bucket.count) ?? [1]));
  const reset = () => {
    setSearch("");
    setStatus("");
    setExpiresWithin("");
    setMismatch("");
    setSelfSigned("");
    setPage(1);
  };
  const toggleSort = (key: string) => {
    if (sort === key) setOrder((current) => (current === "asc" ? "desc" : "asc"));
    else {
      setSort(key);
      setOrder("asc");
    }
    setPage(1);
  };

  if (!selectedCompanyId) return null;

  return (
    <div>
      <PageHeader
        title="SSL/TLS certificates"
        description={
          health
            ? `${health.total} certificates tracked. ${health.expired} expired, ${health.expiring_soon} expiring soon${
                health.closest_expiry_days !== null ? `, closest expiry in ${health.closest_expiry_days} day(s)` : ""
              }.`
            : "Certificate health across observed hosts."
        }
      />

      <div className="mb-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <div className="metric-card">
          <div className="flex items-center gap-2 text-xs text-slate-500"><ShieldCheck className="h-3.5 w-3.5" /> Tracked</div>
          <p className="mt-1 text-2xl font-semibold text-slate-50">{health?.total ?? "—"}</p>
        </div>
        <div className="metric-card">
          <p className="text-xs uppercase tracking-wide text-slate-500">Valid</p>
          <p className="mt-1 text-2xl font-semibold text-low">{health?.valid ?? "—"}</p>
        </div>
        <div className="metric-card">
          <div className="flex items-center gap-2 text-xs text-slate-500"><CalendarClock className="h-3.5 w-3.5" /> Expiring soon</div>
          <p className="mt-1 text-2xl font-semibold text-medium">{health?.expiring_soon ?? "—"}</p>
        </div>
        <div className="metric-card">
          <div className="flex items-center gap-2 text-xs text-slate-500"><TriangleAlert className="h-3.5 w-3.5" /> Expired</div>
          <p className="mt-1 text-2xl font-semibold text-critical">{health?.expired ?? "—"}</p>
        </div>
        <div className="metric-card">
          <div className="flex items-center gap-2 text-xs text-slate-500"><ShieldQuestion className="h-3.5 w-3.5" /> Hostname mismatch</div>
          <p className="mt-1 text-2xl font-semibold text-high">{health?.hostname_mismatch ?? "—"}</p>
        </div>
      </div>

      <div className="mb-4 grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Expiry timeline</CardTitle>
          </CardHeader>
          <CardContent>
            {healthQuery.isLoading ? (
              <Skeleton className="h-24" />
            ) : (
              <div className="space-y-3">
                {health?.expiry_buckets.map((bucket) => (
                  <div key={bucket.key} className="flex items-center gap-3">
                    <span className="w-20 shrink-0 text-xs text-slate-400">{bucket.label}</span>
                    <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-surface-raised">
                      <div
                        className={cn(
                          "h-full rounded-full",
                          bucket.key === "expired" ? "bg-critical" : bucket.key === "7d" ? "bg-high" : bucket.key === "30d" ? "bg-medium" : "bg-brand-500",
                        )}
                        style={{ width: `${Math.round((bucket.count / maxBucket) * 100)}%` }}
                      />
                    </div>
                    <span className="num w-8 text-right text-xs text-slate-300">{bucket.count}</span>
                  </div>
                ))}
                {health?.weak_crypto ? (
                  <p className="text-[11px] text-medium">{health.weak_crypto} certificate(s) use a weak key or deprecated signature.</p>
                ) : null}
                {health?.not_observed ? <p className="text-[11px] text-slate-500">{health.not_observed} record(s) not yet observed live.</p> : null}
              </div>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Top issuers</CardTitle></CardHeader>
          <CardContent>
            {healthQuery.isLoading ? (
              <Skeleton className="h-24" />
            ) : health && health.issuers.length > 0 ? (
              <ul className="space-y-2">
                {health.issuers.map((issuer) => (
                  <li key={issuer.issuer} className="flex items-center justify-between gap-2 text-xs">
                    <span className="truncate text-slate-300">{issuer.issuer}</span>
                    <span className="num text-slate-400">{issuer.count}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-slate-500">No issuer information recorded.</p>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardContent className="space-y-3">
          <div className="flex flex-col gap-2 lg:flex-row lg:flex-wrap lg:items-center">
            <SearchInput value={search} onChange={(value) => { setSearch(value); setPage(1); }} placeholder="Search host, subject or issuer" />
            <Select aria-label="Certificate status" value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }} className="lg:w-40">
              <option value="">Any status</option>
              {STATUSES.map((item) => <option key={item} value={item}>{titleize(item)}</option>)}
            </Select>
            <Select aria-label="Expires within" value={expiresWithin} onChange={(event) => { setExpiresWithin(event.target.value); setPage(1); }} className="lg:w-44">
              <option value="">Any expiry</option>
              <option value="7">Within 7 days</option>
              <option value="14">Within 14 days</option>
              <option value="30">Within 30 days</option>
              <option value="60">Within 60 days</option>
              <option value="90">Within 90 days</option>
            </Select>
            <Select aria-label="Hostname match" value={mismatch} onChange={(event) => { setMismatch(event.target.value); setPage(1); }} className="lg:w-48">
              <option value="">Hostname: any</option>
              <option value="true">Mismatch only</option>
              <option value="false">Matching only</option>
            </Select>
            <Select aria-label="Self-signed" value={selfSigned} onChange={(event) => { setSelfSigned(event.target.value); setPage(1); }} className="lg:w-40">
              <option value="">Self-signed: any</option>
              <option value="true">Self-signed only</option>
              <option value="false">CA-issued only</option>
            </Select>
            {search || status || expiresWithin || mismatch || selfSigned ? (
              <Button variant="ghost" size="sm" onClick={reset}><RotateCcw aria-hidden="true" className="h-3.5 w-3.5" /> Reset</Button>
            ) : null}
          </div>

          {query.isLoading ? (
            <TableLoading columns={7} />
          ) : query.isError ? (
            <ErrorState title="Could not load certificates" message={errorMessage(query.error)} onRetry={() => void query.refetch()} />
          ) : items.length === 0 ? (
            <EmptyState
              icon={ShieldCheck}
              title="No certificates found"
              description="Certificates are recorded when an authorized scan performs a TLS handshake on a host."
              action={search || status || expiresWithin || mismatch || selfSigned ? <Button variant="ghost" size="sm" onClick={reset}>Clear filters</Button> : null}
            />
          ) : (
            <>
              <div className="overflow-x-auto rounded-md border border-border">
                <Table>
                  <THead>
                    <Tr>
                      <Th sortable sortDirection={sort === "host" ? order : undefined} onSort={() => toggleSort("host")}>Host</Th>
                      <Th className="hidden lg:table-cell">Subject</Th>
                      <Th className="hidden lg:table-cell">Issuer</Th>
                      <Th sortable sortDirection={sort === "days_remaining" ? order : undefined} onSort={() => toggleSort("days_remaining")}>Expiry</Th>
                      <Th>Status</Th>
                      <Th className="hidden md:table-cell">Hostname</Th>
                      <Th className="hidden md:table-cell">Source</Th>
                      <Th className="hidden xl:table-cell">Observed</Th>
                    </Tr>
                  </THead>
                  <TBody>
                    {items.map((certificate) => (
                      <Tr key={certificate.id} className="cursor-pointer" onClick={() => setSelectedId(certificate.id)}>
                        <Td>
                          <p className="font-medium text-slate-200">{certificate.host}<span className="text-xs text-slate-500">:{certificate.port}</span></p>
                          {certificate.asset_id ? (
                            <Link
                              to={`/assets/${certificate.asset_id}`}
                              onClick={(event) => event.stopPropagation()}
                              className="text-[11px] text-brand-400 hover:text-brand-300"
                            >
                              {certificate.asset_name ?? "Linked asset"}
                            </Link>
                          ) : null}
                        </Td>
                        <Td className="hidden lg:table-cell"><span className="block max-w-[16rem] truncate text-xs text-slate-300">{certificate.subject_common_name ?? "—"}</span></Td>
                        <Td className="hidden lg:table-cell"><span className="block max-w-[16rem] truncate text-xs text-slate-400">{certificate.issuer_organization ?? certificate.issuer_common_name ?? "—"}</span></Td>
                        <Td>
                          <p className="text-xs text-slate-300">{certificate.not_after ? formatDate(certificate.not_after) : "—"}</p>
                          <Badge tone={daysTone(certificate)}>{daysLabel(certificate)}</Badge>
                        </Td>
                        <Td><StatusBadge status={certificate.status} /></Td>
                        <Td className="hidden md:table-cell">
                          <Badge tone={certificate.hostname_matches ? "low" : "critical"}>{certificate.hostname_matches ? "Matches" : "Mismatch"}</Badge>
                        </Td>
                        <Td className="hidden md:table-cell"><SourceBadge source={certificate.source} /></Td>
                        <Td className="hidden xl:table-cell"><span className="text-xs text-slate-500">{certificate.observed_at ? relativeTime(certificate.observed_at) : "Not observed"}</span></Td>
                      </Tr>
                    ))}
                  </TBody>
                </Table>
              </div>
              <Pagination page={data?.page ?? page} total={data?.total} pageSize={data?.page_size ?? pageSize} onPageChange={setPage} />
            </>
          )}
        </CardContent>
      </Card>

      <p className="mt-4 flex items-start gap-1.5 text-[11px] text-slate-500">
        <Info aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        Certificate state is a snapshot from the last permitted observation. Verify critical expiry or mismatch findings with the owning team before acting.
      </p>

      <CertificateDetail certificateId={selectedId} onClose={() => setSelectedId(null)} />
    </div>
  );
}

export default CertificatesPage;
