import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { Bug, Download, ExternalLink, Pencil, RotateCcw } from "lucide-react";

import { PageHeader } from "@/components/common/PageHeader";
import { CvssBadge, SeverityBadge, SourceBadge, StatusBadge } from "@/components/common/Badges";
import { SearchInput, TableLoading } from "@/components/common/TableState";
import {
  Badge,
  Button,
  Card,
  CardContent,
  EmptyState,
  ErrorState,
  Input,
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
  useToast,
} from "@/components/ui";
import { apiRequest, downloadFile, errorMessage, saveBlob } from "@/lib/api";
import type { CompanyMember, Page, Vulnerability } from "@/lib/apiTypes";
import { titleize } from "@/lib/labels";
import { formatDate, formatNumber, relativeTime } from "@/lib/utils";
import { useAuth } from "@/context/AuthProvider";

const SEVERITIES = ["critical", "high", "medium", "low", "informational"];
const VULN_STATUSES = ["unresolved", "triaged", "in_remediation", "fixed", "accepted_risk", "not_exploitable"];
const EXPLOITABILITY = ["none", "proof_of_concept", "weaponized"];

function toIsoDate(value: string): string | null {
  return value ? `${value}T00:00:00Z` : null;
}

function VulnerabilityDetail({
  vulnerabilityId,
  onClose,
}: {
  vulnerabilityId: string | null;
  onClose: () => void;
}) {
  const { selectedCompanyId, can } = useAuth();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [editOpen, setEditOpen] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [form, setForm] = useState<{
    status: string;
    severity: string;
    confidence: string;
    assignee_id: string;
    due_date: string;
    remediation_note: string;
  } | null>(null);

  const query = useQuery({
    queryKey: ["vulnerability", selectedCompanyId, vulnerabilityId],
    queryFn: () => apiRequest<Vulnerability>(`/companies/${selectedCompanyId}/vulnerabilities/${vulnerabilityId}`),
    enabled: Boolean(selectedCompanyId && vulnerabilityId),
  });

  const membersQuery = useQuery({
    queryKey: ["members", selectedCompanyId],
    queryFn: () => apiRequest<CompanyMember[]>(`/companies/${selectedCompanyId}/members`),
    enabled: Boolean(selectedCompanyId && vulnerabilityId && can("user:read")),
  });

  const updateMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      apiRequest<Vulnerability>(`/companies/${selectedCompanyId}/vulnerabilities/${vulnerabilityId}`, {
        method: "PATCH",
        body: payload,
      }),
    onSuccess: async () => {
      toast({ title: "Vulnerability updated", variant: "success" });
      setEditOpen(false);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["vulnerabilities"] }),
        queryClient.invalidateQueries({ queryKey: ["vulnerability", selectedCompanyId, vulnerabilityId] }),
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
      ]);
    },
    onError: (error) => setEditError(errorMessage(error)),
  });

  const vulnerability = query.data;
  const members = membersQuery.data ?? [];

  const openEdit = () => {
    if (!vulnerability) return;
    setForm({
      status: vulnerability.status,
      severity: vulnerability.severity,
      confidence: vulnerability.confidence,
      assignee_id: vulnerability.assignee_id ?? "",
      due_date: vulnerability.due_date ? vulnerability.due_date.slice(0, 10) : "",
      remediation_note: vulnerability.remediation_note ?? "",
    });
    setEditError(null);
    setEditOpen(true);
  };

  const references = (vulnerability?.references ?? []).filter(
    (reference): reference is string => typeof reference === "string" && reference.startsWith("http"),
  );

  return (
    <>
      <Modal
        open={Boolean(vulnerabilityId)}
        onClose={onClose}
        title={vulnerability ? `${vulnerability.cve_id} — ${vulnerability.title}` : "Vulnerability detail"}
        description={vulnerability ? `${vulnerability.affected_product ?? "Unknown product"} ${vulnerability.affected_version ?? ""} · discovered ${relativeTime(vulnerability.discovered_at)}` : undefined}
        size="lg"
        footer={
          <>
            <Button variant="ghost" size="sm" onClick={onClose}>Close</Button>
            {can("vulnerability:write") && vulnerability ? (
              <Button size="sm" onClick={openEdit}><Pencil aria-hidden="true" className="h-4 w-4" /> Update</Button>
            ) : null}
          </>
        }
      >
        {query.isLoading ? (
          <div className="space-y-3"><Skeleton className="h-6 w-56" /><Skeleton className="h-32" /></div>
        ) : query.isError ? (
          <ErrorState title="Could not load vulnerability" message={errorMessage(query.error)} onRetry={() => void query.refetch()} />
        ) : vulnerability ? (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <SeverityBadge severity={vulnerability.severity} />
              <CvssBadge score={vulnerability.cvss_base_score} />
              <StatusBadge status={vulnerability.status} />
              <SourceBadge source={vulnerability.source} provenance={vulnerability.provenance} />
              {vulnerability.in_ransomware_catalog ? <Badge tone="critical">Ransomware catalog</Badge> : null}
              {vulnerability.exploitability ? <Badge tone={vulnerability.exploitability === "weaponized" ? "critical" : "high"}>{titleize(vulnerability.exploitability)}</Badge> : null}
            </div>

            <dl className="grid gap-x-6 sm:grid-cols-2">
              {[
                ["Asset", vulnerability.asset_name ?? "Unlinked asset"],
                ["Affected product", vulnerability.affected_product ?? "—"],
                ["Affected version", vulnerability.affected_version ?? "—"],
                ["Fixed version", vulnerability.fixed_version ?? "No fix recorded"],
                ["Confidence", titleize(vulnerability.confidence)],
                ["Assignee", vulnerability.assignee_name ?? "Unassigned"],
                ["Discovered", vulnerability.discovered_at ? formatDate(vulnerability.discovered_at) : "—"],
                ["Due date", vulnerability.due_date ? formatDate(vulnerability.due_date) : "—"],
                ["Resolved", vulnerability.resolved_at ? formatDate(vulnerability.resolved_at) : "Not resolved"],
                ["CVSS vector", vulnerability.cvss_vector ?? "—"],
              ].map(([label, value]) => (
                <div key={label} className="border-b border-border/60 py-2">
                  <dt className="text-[11px] uppercase tracking-wide text-slate-500">{label}</dt>
                  <dd className="mt-0.5 break-words text-xs text-slate-300">{value}</dd>
                </div>
              ))}
            </dl>

            <section>
              <h3 className="text-xs font-medium uppercase tracking-wide text-slate-500">Description</h3>
              <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed text-slate-300">{vulnerability.description ?? "No description supplied."}</p>
            </section>
            <section>
              <h3 className="text-xs font-medium uppercase tracking-wide text-slate-500">Recommendation</h3>
              <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed text-slate-300">{vulnerability.recommendation ?? "No recommendation recorded."}</p>
            </section>
            <section>
              <h3 className="text-xs font-medium uppercase tracking-wide text-slate-500">Remediation note</h3>
              <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed text-slate-300">{vulnerability.remediation_note ?? "No remediation note yet."}</p>
            </section>

            {references.length > 0 ? (
              <section>
                <h3 className="text-xs font-medium uppercase tracking-wide text-slate-500">References</h3>
                <ul className="mt-1 space-y-1">
                  {references.map((reference) => (
                    <li key={reference}>
                      <a href={reference} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 break-all text-xs text-brand-400 hover:text-brand-300">
                        {reference} <ExternalLink aria-hidden="true" className="h-3 w-3 shrink-0" />
                      </a>
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}

            {vulnerability.asset_id ? (
              <Link to={`/assets/${vulnerability.asset_id}`} className="inline-block text-xs font-medium text-brand-400 hover:text-brand-300" onClick={onClose}>
                Open linked asset
              </Link>
            ) : null}
          </div>
        ) : null}
      </Modal>

      <Modal
        open={editOpen && Boolean(form)}
        onClose={() => setEditOpen(false)}
        title="Update vulnerability"
        description="Changes are audit-logged. Marking an item fixed does not prove the fix; verification still needs evidence."
        footer={
          <>
            <Button variant="ghost" size="sm" onClick={() => setEditOpen(false)} disabled={updateMutation.isPending}>Cancel</Button>
            <Button
              size="sm"
              disabled={updateMutation.isPending}
              onClick={() => {
                if (!form) return;
                setEditError(null);
                updateMutation.mutate({
                  status: form.status,
                  severity: form.severity,
                  confidence: form.confidence,
                  assignee_id: form.assignee_id || null,
                  due_date: toIsoDate(form.due_date),
                  remediation_note: form.remediation_note.trim() || null,
                });
              }}
            >
              {updateMutation.isPending ? "Saving…" : "Save changes"}
            </Button>
          </>
        }
      >
        {form ? (
          <div className="space-y-4">
            {editError ? (
              <p role="alert" className="rounded-md border border-critical/30 bg-critical/10 px-3 py-2 text-xs text-critical">{editError}</p>
            ) : null}
            <div className="grid gap-4 sm:grid-cols-2">
              <Select label="Status" value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value })}>
                {VULN_STATUSES.map((status) => <option key={status} value={status}>{titleize(status)}</option>)}
              </Select>
              <Select label="Severity" value={form.severity} onChange={(event) => setForm({ ...form, severity: event.target.value })}>
                {SEVERITIES.map((severity) => <option key={severity} value={severity}>{titleize(severity)}</option>)}
              </Select>
              <Select label="Confidence" value={form.confidence} onChange={(event) => setForm({ ...form, confidence: event.target.value })}>
                <option value="confirmed">Confirmed</option>
                <option value="potential">Potential</option>
              </Select>
              {can("user:read") ? (
                <Select label="Assignee" value={form.assignee_id} onChange={(event) => setForm({ ...form, assignee_id: event.target.value })}>
                  <option value="">Unassigned</option>
                  {members.map((member) => <option key={member.user_id} value={member.user_id}>{member.full_name}</option>)}
                </Select>
              ) : null}
              <Input label="Due date" type="date" value={form.due_date} onChange={(event) => setForm({ ...form, due_date: event.target.value })} />
            </div>
            <div>
              <label htmlFor="vuln-note" className="text-xs font-medium text-slate-300">Remediation note</label>
              <textarea
                id="vuln-note"
                rows={3}
                value={form.remediation_note}
                onChange={(event) => setForm({ ...form, remediation_note: event.target.value })}
                className="mt-1 w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-slate-200 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
              />
            </div>
          </div>
        ) : null}
      </Modal>
    </>
  );
}

export function VulnerabilitiesPage() {
  const { selectedCompanyId, can } = useAuth();
  const { toast } = useToast();
  const [searchParams, setSearchParams] = useSearchParams();
  const focus = searchParams.get("focus");
  const [search, setSearch] = useState("");
  const [severity, setSeverity] = useState("");
  const [status, setStatus] = useState("");
  const [confidence, setConfidence] = useState("");
  const [exploitability, setExploitability] = useState("");
  const [ransomwareOnly, setRansomwareOnly] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize] = useState(25);
  const [sort, setSort] = useState("cvss_base_score");
  const [order, setOrder] = useState<"asc" | "desc">("desc");
  const [exporting, setExporting] = useState(false);

  const filters = {
    q: search.trim() || undefined,
    severity: severity ? [severity] : undefined,
    status: status || undefined,
    confidence: confidence || undefined,
    exploitability: exploitability || undefined,
    ransomware_only: ransomwareOnly === "true" ? true : undefined,
  };

  const query = useQuery({
    queryKey: ["vulnerabilities", selectedCompanyId, filters, page, pageSize, sort, order],
    queryFn: () =>
      apiRequest<Page<Vulnerability>>(`/companies/${selectedCompanyId}/vulnerabilities`, {
        params: { ...filters, page, page_size: pageSize, sort, order },
      }),
    enabled: Boolean(selectedCompanyId),
    placeholderData: (previous) => previous,
  });

  const data = query.data;
  const items = data?.items ?? [];
  const reset = () => {
    setSearch("");
    setSeverity("");
    setStatus("");
    setConfidence("");
    setExploitability("");
    setRansomwareOnly("");
    setPage(1);
  };
  const toggleSort = (key: string) => {
    if (sort === key) setOrder((current) => (current === "desc" ? "asc" : "desc"));
    else {
      setSort(key);
      setOrder("desc");
    }
    setPage(1);
  };
  const setFocus = (id: string | null) => {
    const next = new URLSearchParams(searchParams);
    if (id) next.set("focus", id);
    else next.delete("focus");
    setSearchParams(next, { replace: true });
  };
  const exportCsv = async () => {
    setExporting(true);
    try {
      const { blob, filename } = await downloadFile(`/companies/${selectedCompanyId}/vulnerabilities/export`, filters);
      saveBlob(blob, filename ?? "vulnerabilities.csv");
    } catch (error) {
      toast({ title: "Export failed", description: errorMessage(error), variant: "error" });
    } finally {
      setExporting(false);
    }
  };

  if (!selectedCompanyId) return null;

  return (
    <div>
      <PageHeader
        title="Vulnerability management"
        description={
          data
            ? `${formatNumber(data.total)} CVE-associated record(s) match the filters. CVEs are only listed when a source associated them with an asset; the platform does not invent findings.`
            : "CVE-linked weaknesses with CVSS, exploitability signals and a remediation workflow."
        }
        actions={
          can("report:export") ? (
            <Button variant="ghost" size="sm" onClick={() => void exportCsv()} disabled={exporting}>
              <Download aria-hidden="true" className="h-4 w-4" /> {exporting ? "Exporting…" : "Export CSV"}
            </Button>
          ) : null
        }
      />

      <div className="mb-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div className="metric-card">
          <p className="text-xs uppercase tracking-wide text-slate-500">Matching CVEs</p>
          <p className="mt-1 text-2xl font-semibold text-slate-50">{data ? formatNumber(data.total) : "—"}</p>
        </div>
        <div className="metric-card">
          <p className="text-xs uppercase tracking-wide text-slate-500">Critical on page</p>
          <p className="mt-1 text-2xl font-semibold text-critical">{items.filter((item) => item.severity === "critical").length}</p>
        </div>
        <div className="metric-card">
          <p className="text-xs uppercase tracking-wide text-slate-500">Weaponized on page</p>
          <p className="mt-1 text-2xl font-semibold text-high">{items.filter((item) => item.exploitability === "weaponized").length}</p>
        </div>
        <div className="metric-card">
          <p className="text-xs uppercase tracking-wide text-slate-500">In ransomware catalog</p>
          <p className="mt-1 text-2xl font-semibold text-critical">{items.filter((item) => item.in_ransomware_catalog).length}</p>
        </div>
      </div>

      <Card>
        <CardContent className="space-y-3">
          <div className="flex flex-col gap-2 xl:flex-row xl:flex-wrap xl:items-center">
            <SearchInput value={search} onChange={(value) => { setSearch(value); setPage(1); }} placeholder="Search CVE, title or product" />
            <Select aria-label="Severity" value={severity} onChange={(event) => { setSeverity(event.target.value); setPage(1); }} className="xl:w-36">
              <option value="">Any severity</option>
              {SEVERITIES.map((value) => <option key={value} value={value}>{titleize(value)}</option>)}
            </Select>
            <Select aria-label="Status" value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }} className="xl:w-44">
              <option value="">Any status</option>
              {VULN_STATUSES.map((value) => <option key={value} value={value}>{titleize(value)}</option>)}
            </Select>
            <Select aria-label="Confidence" value={confidence} onChange={(event) => { setConfidence(event.target.value); setPage(1); }} className="xl:w-40">
              <option value="">Any confidence</option>
              <option value="confirmed">Confirmed</option>
              <option value="potential">Potential</option>
            </Select>
            <Select aria-label="Exploitability" value={exploitability} onChange={(event) => { setExploitability(event.target.value); setPage(1); }} className="xl:w-44">
              <option value="">Any exploitability</option>
              {EXPLOITABILITY.map((value) => <option key={value} value={value}>{titleize(value)}</option>)}
            </Select>
            <Select aria-label="Ransomware catalog" value={ransomwareOnly} onChange={(event) => { setRansomwareOnly(event.target.value); setPage(1); }} className="xl:w-52">
              <option value="">Ransomware: any</option>
              <option value="true">In ransomware catalog</option>
            </Select>
            {search || severity || status || confidence || exploitability || ransomwareOnly ? (
              <Button variant="ghost" size="sm" onClick={reset}><RotateCcw aria-hidden="true" className="h-3.5 w-3.5" /> Reset</Button>
            ) : null}
          </div>

          {query.isLoading ? (
            <TableLoading columns={8} />
          ) : query.isError ? (
            <ErrorState title="Could not load vulnerabilities" message={errorMessage(query.error)} onRetry={() => void query.refetch()} />
          ) : items.length === 0 ? (
            <EmptyState
              icon={Bug}
              title="No vulnerabilities match"
              description="CVE records appear when an authorized discovery or import associates a known vulnerability with an asset."
              action={search || severity || status || confidence || exploitability || ransomwareOnly ? <Button variant="ghost" size="sm" onClick={reset}>Clear filters</Button> : null}
            />
          ) : (
            <>
              <div className="overflow-x-auto rounded-md border border-border">
                <Table>
                  <THead>
                    <Tr>
                      <Th>CVE</Th>
                      <Th sortable sortDirection={sort === "severity" ? order : undefined} onSort={() => toggleSort("severity")}>Severity</Th>
                      <Th sortable align="right" sortDirection={sort === "cvss_base_score" ? order : undefined} onSort={() => toggleSort("cvss_base_score")}>CVSS</Th>
                      <Th className="hidden lg:table-cell">Product</Th>
                      <Th>Status</Th>
                      <Th className="hidden xl:table-cell">Exploitability</Th>
                      <Th className="hidden xl:table-cell">Assignee</Th>
                      <Th className="hidden md:table-cell">Discovered</Th>
                    </Tr>
                  </THead>
                  <TBody>
                    {items.map((vulnerability) => (
                      <Tr key={vulnerability.id} className="cursor-pointer" onClick={() => setFocus(vulnerability.id)}>
                        <Td>
                          <button
                            type="button"
                            onClick={(event) => { event.stopPropagation(); setFocus(vulnerability.id); }}
                            className="block max-w-[24rem] truncate text-left font-medium text-slate-200 hover:text-brand-400"
                            title={vulnerability.title}
                          >
                            <span className="num text-brand-400">{vulnerability.cve_id}</span>{" "}
                            {vulnerability.title}
                          </button>
                          <p className="mt-0.5 truncate text-[11px] text-slate-500">
                            {vulnerability.asset_id ? (
                              <Link to={`/assets/${vulnerability.asset_id}`} onClick={(event) => event.stopPropagation()} className="hover:text-brand-300">
                                {vulnerability.asset_name ?? "asset"}
                              </Link>
                            ) : "unlinked"}{" "}
                            · {titleize(vulnerability.confidence)}
                          </p>
                        </Td>
                        <Td><SeverityBadge severity={vulnerability.severity} /></Td>
                        <Td align="right"><CvssBadge score={vulnerability.cvss_base_score} /></Td>
                        <Td className="hidden lg:table-cell">
                          <p className="text-xs text-slate-300">{vulnerability.affected_product ?? "—"}</p>
                          <p className="text-[11px] text-slate-500">
                            {vulnerability.affected_version ?? "unknown"}
                            {vulnerability.fixed_version ? ` → ${vulnerability.fixed_version}` : ""}
                          </p>
                        </Td>
                        <Td><StatusBadge status={vulnerability.status} /></Td>
                        <Td className="hidden xl:table-cell">
                          <div className="flex flex-wrap gap-1">
                            {vulnerability.exploitability ? (
                              <Badge tone={vulnerability.exploitability === "weaponized" ? "critical" : "high"}>{titleize(vulnerability.exploitability)}</Badge>
                            ) : <span className="text-xs text-slate-500">—</span>}
                            {vulnerability.in_ransomware_catalog ? <Badge tone="critical">Ransomware</Badge> : null}
                          </div>
                        </Td>
                        <Td className="hidden xl:table-cell"><span className="text-xs text-slate-300">{vulnerability.assignee_name ?? "Unassigned"}</span></Td>
                        <Td className="hidden md:table-cell"><span className="text-xs text-slate-500">{vulnerability.discovered_at ? relativeTime(vulnerability.discovered_at) : "—"}</span></Td>
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

      <VulnerabilityDetail vulnerabilityId={focus} onClose={() => setFocus(null)} />
    </div>
  );
}

export default VulnerabilitiesPage;
