import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Activity, Check, History, RotateCcw, ShieldAlert, TrendingUp } from "lucide-react";

import { PageHeader } from "@/components/common/PageHeader";
import { SeverityBadge } from "@/components/common/Badges";
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
  useToast,
} from "@/components/ui";
import { apiRequest, errorMessage } from "@/lib/api";
import type { ChangeSummary, ConfigurationChange, Page } from "@/lib/apiTypes";
import { titleize } from "@/lib/labels";
import { formatDateTime, formatNumber, relativeTime } from "@/lib/utils";
import { useAuth } from "@/context/AuthProvider";

const SEVERITIES = ["critical", "high", "medium", "low", "informational"];

function ChangeDetail({
  change,
  onClose,
  onAcknowledge,
  acknowledging,
  canAcknowledge,
}: {
  change: ConfigurationChange | null;
  onClose: () => void;
  onAcknowledge: () => void;
  acknowledging: boolean;
  canAcknowledge: boolean;
}) {
  return (
    <Modal
      open={Boolean(change)}
      onClose={onClose}
      title={change?.summary ?? "Configuration change"}
      description={change ? `${titleize(change.change_type)} · observed ${relativeTime(change.occurred_at)}` : undefined}
      size="lg"
      footer={
        <>
          <Button variant="ghost" size="sm" onClick={onClose}>Close</Button>
          {canAcknowledge && change && !change.acknowledged_at ? (
            <Button size="sm" onClick={onAcknowledge} disabled={acknowledging}>
              <Check aria-hidden="true" className="h-4 w-4" />
              {acknowledging ? "Acknowledging…" : "Acknowledge"}
            </Button>
          ) : null}
        </>
      }
    >
      {change ? (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <SeverityBadge severity={change.severity} />
            <Badge tone="neutral">{titleize(change.change_type)}</Badge>
            {change.is_suspicious ? <Badge tone="high">Suspicious</Badge> : null}
            {change.is_unplanned_exposure ? <Badge tone="critical">Unplanned exposure</Badge> : null}
            {change.is_expected ? <Badge tone="low">Expected</Badge> : null}
            {change.acknowledged_at ? <Badge tone="low">Acknowledged</Badge> : <Badge tone="medium">Unacknowledged</Badge>}
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-md bg-surface-raised/60 px-3 py-2">
              <p className="text-[11px] uppercase tracking-wide text-slate-500">Field</p>
              <p className="text-xs text-slate-200">{change.field}</p>
            </div>
            <div className="rounded-md bg-surface-raised/60 px-3 py-2">
              <p className="text-[11px] uppercase tracking-wide text-slate-500">Asset</p>
              {change.asset_id ? (
                <Link to={`/assets/${change.asset_id}`} className="text-xs text-brand-400 hover:text-brand-300">{change.asset_name ?? "Linked asset"}</Link>
              ) : (
                <p className="text-xs text-slate-400">Unlinked</p>
              )}
            </div>
            <div className="rounded-md bg-surface-raised/60 px-3 py-2 sm:col-span-2">
              <p className="text-[11px] uppercase tracking-wide text-slate-500">Observed at</p>
              <p className="text-xs text-slate-200">{formatDateTime(change.occurred_at)}</p>
              {change.acknowledged_at ? (
                <p className="mt-1 text-[11px] text-slate-500">Acknowledged {formatDateTime(change.acknowledged_at)}</p>
              ) : null}
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <p className="mb-1 text-[11px] uppercase tracking-wide text-slate-500">Previous value</p>
              <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-all rounded-md border border-border bg-surface px-3 py-2 text-xs text-slate-400">{change.old_value ?? "—"}</pre>
            </div>
            <div>
              <p className="mb-1 text-[11px] uppercase tracking-wide text-slate-500">New value</p>
              <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-all rounded-md border border-border bg-surface px-3 py-2 text-xs text-slate-200">{change.new_value ?? "—"}</pre>
            </div>
          </div>

          {Object.keys(change.detail).length > 0 ? (
            <div>
              <p className="mb-1 text-[11px] uppercase tracking-wide text-slate-500">Detail</p>
              <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-md bg-surface-raised px-3 py-2 text-[11px] text-slate-400">{JSON.stringify(change.detail, null, 2)}</pre>
            </div>
          ) : null}

          <p className="text-[11px] text-slate-500">
            Source {titleize(change.source)}. Acknowledging records that the change was reviewed; it does not revert it.
          </p>
        </div>
      ) : null}
    </Modal>
  );
}

export function ChangesPage() {
  const { selectedCompanyId, can, enums } = useAuth();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [search, setSearch] = useState("");
  const [changeType, setChangeType] = useState("");
  const [severity, setSeverity] = useState("");
  const [suspiciousOnly, setSuspiciousOnly] = useState("");
  const [acknowledged, setAcknowledged] = useState("");
  const [since, setSince] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize] = useState(25);
  const [selected, setSelected] = useState<ConfigurationChange | null>(null);

  const sinceIso = (() => {
    if (!since) return undefined;
    const days = Number(since);
    const date = new Date();
    date.setDate(date.getDate() - days);
    return date.toISOString();
  })();

  const filters = {
    q: search.trim() || undefined,
    change_type: changeType || undefined,
    severity: severity || undefined,
    suspicious_only: suspiciousOnly === "true" ? true : undefined,
    unplanned_only: suspiciousOnly === "unplanned" ? true : undefined,
    acknowledged: acknowledged === "" ? undefined : acknowledged === "true",
    since: sinceIso,
  };

  const summaryQuery = useQuery({
    queryKey: ["changes-summary", selectedCompanyId],
    queryFn: () => apiRequest<ChangeSummary>(`/companies/${selectedCompanyId}/changes/summary`),
    enabled: Boolean(selectedCompanyId),
  });

  const query = useQuery({
    queryKey: ["changes", selectedCompanyId, filters, page, pageSize],
    queryFn: () =>
      apiRequest<Page<ConfigurationChange>>(`/companies/${selectedCompanyId}/changes`, {
        params: { ...filters, page, page_size: pageSize, sort: "occurred_at", order: "desc" },
      }),
    enabled: Boolean(selectedCompanyId),
    placeholderData: (previous) => previous,
  });

  const ackMutation = useMutation({
    mutationFn: (changeId: string) =>
      apiRequest<ConfigurationChange>(`/companies/${selectedCompanyId}/changes/${changeId}/acknowledge`, { method: "POST" }),
    onSuccess: async (updated) => {
      setSelected(updated);
      toast({ title: "Change acknowledged", variant: "success" });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["changes"] }),
        queryClient.invalidateQueries({ queryKey: ["changes-summary", selectedCompanyId] }),
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
      ]);
    },
    onError: (error) => toast({ title: "Could not acknowledge change", description: errorMessage(error), variant: "error" }),
  });

  const summary = summaryQuery.data;
  const data = query.data;
  const items = data?.items ?? [];
  const reset = () => {
    setSearch("");
    setChangeType("");
    setSeverity("");
    setSuspiciousOnly("");
    setAcknowledged("");
    setSince("");
    setPage(1);
  };
  const maxTypeCount = Math.max(1, ...(summary?.by_type.map((entry) => entry.count) ?? [1]));
  const activeFilterCount = [search, changeType, severity, suspiciousOnly, acknowledged, since].filter(Boolean).length;

  if (!selectedCompanyId) return null;

  return (
    <div>
      <PageHeader
        title="Change history"
        description="DNS, IP, service, certificate and cloud configuration changes detected between observations. Acknowledging a change records review, not acceptance of risk."
      />

      <div className="mb-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div className="metric-card">
          <div className="flex items-center gap-2 text-xs text-slate-500"><History className="h-3.5 w-3.5" /> Changes (30 days)</div>
          <p className="mt-1 text-2xl font-semibold text-slate-50">{summary ? formatNumber(summary.total_30d) : "—"}</p>
        </div>
        <div className="metric-card">
          <div className="flex items-center gap-2 text-xs text-slate-500"><ShieldAlert className="h-3.5 w-3.5" /> Suspicious (30 days)</div>
          <p className="mt-1 text-2xl font-semibold text-high">{summary ? formatNumber(summary.suspicious_30d) : "—"}</p>
        </div>
        <div className="metric-card">
          <div className="flex items-center gap-2 text-xs text-slate-500"><TrendingUp className="h-3.5 w-3.5" /> Unplanned exposure</div>
          <p className="mt-1 text-2xl font-semibold text-critical">{summary ? formatNumber(summary.unplanned_exposure_30d) : "—"}</p>
        </div>
        <div className="metric-card">
          <p className="text-xs uppercase tracking-wide text-slate-500">Distinct change types</p>
          <p className="mt-1 text-2xl font-semibold text-slate-50">{summary ? summary.by_type.filter((entry) => entry.count > 0).length : "—"}</p>
        </div>
      </div>

      <div className="mb-4 grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Changes by type (30 days)</CardTitle></CardHeader>
          <CardContent>
            {summaryQuery.isLoading ? (
              <Skeleton className="h-28" />
            ) : summary ? (
              <div className="space-y-2">
                {summary.by_type.filter((entry) => entry.count > 0).length === 0 ? (
                  <p className="text-xs text-slate-500">No changes recorded in the last 30 days.</p>
                ) : (
                  summary.by_type.filter((entry) => entry.count > 0).map((entry) => (
                    <div key={entry.type} className="flex items-center gap-3">
                      <span className="w-36 shrink-0 truncate text-xs text-slate-400" title={titleize(entry.type)}>{titleize(entry.type)}</span>
                      <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-raised">
                        <div className="h-full rounded-full bg-brand-500" style={{ width: `${Math.round((entry.count / maxTypeCount) * 100)}%` }} />
                      </div>
                      <span className="num w-6 text-right text-xs text-slate-300">{entry.count}</span>
                    </div>
                  ))
                )}
              </div>
            ) : null}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Changes by severity (30 days)</CardTitle></CardHeader>
          <CardContent>
            {summaryQuery.isLoading ? (
              <Skeleton className="h-28" />
            ) : summary ? (
              <div className="space-y-2">
                {summary.by_severity.map((entry) => {
                  const total = summary.total_30d || 1;
                  return (
                    <div key={entry.severity} className="flex items-center gap-3">
                      <span className="w-24 shrink-0"><SeverityBadge severity={entry.severity} /></span>
                      <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-raised">
                        <div className="h-full rounded-full bg-brand-500" style={{ width: `${Math.round((entry.count / total) * 100)}%` }} />
                      </div>
                      <span className="num w-6 text-right text-xs text-slate-300">{entry.count}</span>
                    </div>
                  );
                })}
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardContent className="space-y-3">
          <div className="flex flex-col gap-2 xl:flex-row xl:flex-wrap xl:items-center">
            <SearchInput value={search} onChange={(value) => { setSearch(value); setPage(1); }} placeholder="Search summary or field" />
            <Select aria-label="Change type" value={changeType} onChange={(event) => { setChangeType(event.target.value); setPage(1); }} className="xl:w-48">
              <option value="">All change types</option>
              {(enums?.change_types ?? []).map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </Select>
            <Select aria-label="Severity" value={severity} onChange={(event) => { setSeverity(event.target.value); setPage(1); }} className="xl:w-36">
              <option value="">Any severity</option>
              {SEVERITIES.map((value) => <option key={value} value={value}>{titleize(value)}</option>)}
            </Select>
            <Select aria-label="Risk flags" value={suspiciousOnly} onChange={(event) => { setSuspiciousOnly(event.target.value); setPage(1); }} className="xl:w-52">
              <option value="">All changes</option>
              <option value="true">Suspicious only</option>
              <option value="unplanned">Unplanned exposure only</option>
            </Select>
            <Select aria-label="Acknowledged" value={acknowledged} onChange={(event) => { setAcknowledged(event.target.value); setPage(1); }} className="xl:w-48">
              <option value="">Acknowledged: any</option>
              <option value="false">Unacknowledged</option>
              <option value="true">Acknowledged</option>
            </Select>
            <Select aria-label="Since" value={since} onChange={(event) => { setSince(event.target.value); setPage(1); }} className="xl:w-36">
              <option value="">Any time</option>
              <option value="1">Last 24 hours</option>
              <option value="7">Last 7 days</option>
              <option value="30">Last 30 days</option>
              <option value="90">Last 90 days</option>
            </Select>
            {activeFilterCount > 0 ? (
              <Button variant="ghost" size="sm" onClick={reset}>
                <RotateCcw aria-hidden="true" className="h-3.5 w-3.5" /> Reset <Badge tone="neutral">{activeFilterCount}</Badge>
              </Button>
            ) : null}
          </div>

          {query.isLoading ? (
            <TableLoading columns={7} />
          ) : query.isError ? (
            <ErrorState title="Could not load changes" message={errorMessage(query.error)} onRetry={() => void query.refetch()} />
          ) : items.length === 0 ? (
            <EmptyState
              icon={Activity}
              title={activeFilterCount > 0 ? "No changes match these filters" : "No configuration changes yet"}
              description={
                activeFilterCount > 0
                  ? "Clear the filters to widen the search."
                  : "Changes appear when two observations of the same asset differ — for example a DNS record, exposed port or certificate rotation."
              }
              action={activeFilterCount > 0 ? <Button variant="ghost" size="sm" onClick={reset}>Clear filters</Button> : null}
            />
          ) : (
            <>
              <div className="overflow-x-auto rounded-md border border-border">
                <Table>
                  <THead>
                    <Tr>
                      <Th>Change</Th>
                      <Th className="hidden lg:table-cell">Type</Th>
                      <Th>Severity</Th>
                      <Th className="hidden xl:table-cell">Asset</Th>
                      <Th className="hidden lg:table-cell">Value</Th>
                      <Th>Flags</Th>
                      <Th>Occurred</Th>
                      <Th>Review</Th>
                    </Tr>
                  </THead>
                  <TBody>
                    {items.map((change) => (
                      <Tr key={change.id} className="cursor-pointer" onClick={() => setSelected(change)}>
                        <Td>
                          <p className="max-w-[20rem] truncate font-medium text-slate-200" title={change.summary}>{change.summary}</p>
                          <p className="text-[11px] text-slate-500">{change.field}</p>
                        </Td>
                        <Td className="hidden lg:table-cell"><span className="text-xs text-slate-400">{titleize(change.change_type)}</span></Td>
                        <Td><SeverityBadge severity={change.severity} /></Td>
                        <Td className="hidden xl:table-cell">
                          {change.asset_id ? (
                            <Link to={`/assets/${change.asset_id}`} onClick={(event) => event.stopPropagation()} className="block max-w-[12rem] truncate text-xs text-slate-300 hover:text-brand-400">
                              {change.asset_name ?? "asset"}
                            </Link>
                          ) : <span className="text-xs text-slate-500">Unlinked</span>}
                        </Td>
                        <Td className="hidden lg:table-cell">
                          <p className="max-w-[16rem] truncate text-[11px] text-slate-500" title={`${change.old_value ?? "—"} → ${change.new_value ?? "—"}`}>
                            {change.old_value ?? "—"} → {change.new_value ?? "—"}
                          </p>
                        </Td>
                        <Td>
                          <div className="flex flex-wrap gap-1">
                            {change.is_suspicious ? <Badge tone="high">Suspicious</Badge> : null}
                            {change.is_unplanned_exposure ? <Badge tone="critical">Unplanned</Badge> : null}
                            {!change.is_suspicious && !change.is_unplanned_exposure ? <span className="text-xs text-slate-500">—</span> : null}
                          </div>
                        </Td>
                        <Td><span className="text-xs text-slate-400" title={formatDateTime(change.occurred_at)}>{relativeTime(change.occurred_at)}</span></Td>
                        <Td>
                          {change.acknowledged_at ? <Badge tone="low">Acknowledged</Badge> : <Badge tone="medium">Open</Badge>}
                        </Td>
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

      <p className="mt-4 text-[11px] text-slate-500">
        Absence of a change is not proof that nothing changed — it means no permitted observation detected a difference.
      </p>

      <ChangeDetail
        change={selected}
        onClose={() => setSelected(null)}
        onAcknowledge={() => selected && ackMutation.mutate(selected.id)}
        acknowledging={ackMutation.isPending}
        canAcknowledge={can("alert:write")}
      />
    </div>
  );
}

export default ChangesPage;
