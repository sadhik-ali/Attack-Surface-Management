import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import {
  Download,
  FileText,
  ListChecks,
  MessageSquarePlus,
  Pencil,
  RotateCcw,
  ShieldCheck,
} from "lucide-react";

import { PageHeader } from "@/components/common/PageHeader";
import { CvssBadge, RiskBadge, SeverityBadge, StatusBadge } from "@/components/common/Badges";
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
  Tabs,
  Table,
  TBody,
  Td,
  Th,
  THead,
  Tr,
  useToast,
} from "@/components/ui";
import { apiRequest, downloadFile, errorMessage, saveBlob } from "@/lib/api";
import type {
  CompanyMember,
  Finding,
  FindingDetail,
  Page,
  RemediationTask,
} from "@/lib/apiTypes";
import { titleize } from "@/lib/labels";
import { formatDate, formatNumber, relativeTime } from "@/lib/utils";
import { useAuth } from "@/context/AuthProvider";

const SEVERITIES = ["critical", "high", "medium", "low", "informational"];
const CONFIDENCE = ["confirmed", "potential"];
const TASK_PRIORITIES = ["urgent", "high", "medium", "low"];
const TASK_STATUSES = ["open", "in_progress", "blocked", "resolved", "verified", "wont_fix"];

function toIsoDate(value: string): string | null {
  if (!value) return null;
  return `${value}T00:00:00Z`;
}

function isoToDate(value: string | null): string {
  return value ? value.slice(0, 10) : "";
}

function FindingDetailModal({
  findingId,
  onClose,
}: {
  findingId: string | null;
  onClose: () => void;
}) {
  const { selectedCompanyId, can } = useAuth();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [tab, setTab] = useState("details");
  const [note, setNote] = useState("");
  const [editOpen, setEditOpen] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<{
    status: string;
    severity: string;
    assignee_id: string;
    due_date: string;
    recommendation: string;
    remediation_notes: string;
  } | null>(null);
  const [taskForm, setTaskForm] = useState({ title: "", priority: "medium", assignee_id: "", due_date: "" });

  const detailQuery = useQuery({
    queryKey: ["finding-detail", selectedCompanyId, findingId],
    queryFn: () => apiRequest<FindingDetail>(`/companies/${selectedCompanyId}/findings/${findingId}`),
    enabled: Boolean(selectedCompanyId && findingId),
  });

  const membersQuery = useQuery({
    queryKey: ["members", selectedCompanyId],
    queryFn: () => apiRequest<CompanyMember[]>(`/companies/${selectedCompanyId}/members`),
    enabled: Boolean(selectedCompanyId && findingId && can("user:read")),
  });

  const invalidate = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["findings"] }),
      queryClient.invalidateQueries({ queryKey: ["finding-detail", selectedCompanyId, findingId] }),
      queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
    ]);
  };

  const updateMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      apiRequest<Finding>(`/companies/${selectedCompanyId}/findings/${findingId}`, { method: "PATCH", body: payload }),
    onSuccess: async () => {
      toast({ title: "Finding updated", variant: "success" });
      setEditOpen(false);
      await invalidate();
    },
    onError: (error) => setEditError(errorMessage(error)),
  });

  const noteMutation = useMutation({
    mutationFn: () =>
      apiRequest<Finding>(`/companies/${selectedCompanyId}/findings/${findingId}/notes`, {
        method: "POST",
        body: { note: note.trim() },
      }),
    onSuccess: async () => {
      setNote("");
      toast({ title: "Note added", variant: "success" });
      await invalidate();
    },
    onError: (error) => toast({ title: "Could not add note", description: errorMessage(error), variant: "error" }),
  });

  const taskMutation = useMutation({
    mutationFn: () =>
      apiRequest<RemediationTask>(`/companies/${selectedCompanyId}/findings/${findingId}/tasks`, {
        method: "POST",
        body: {
          title: taskForm.title.trim(),
          priority: taskForm.priority,
          assignee_id: taskForm.assignee_id || null,
          due_date: toIsoDate(taskForm.due_date),
        },
      }),
    onSuccess: async () => {
      setTaskForm({ title: "", priority: "medium", assignee_id: "", due_date: "" });
      toast({ title: "Remediation task created", variant: "success" });
      await invalidate();
    },
    onError: (error) => toast({ title: "Could not create task", description: errorMessage(error), variant: "error" }),
  });

  const taskStatusMutation = useMutation({
    mutationFn: ({ taskId, status }: { taskId: string; status: string }) =>
      apiRequest<RemediationTask>(`/companies/${selectedCompanyId}/findings/${findingId}/tasks/${taskId}`, {
        method: "PATCH",
        body: { status },
      }),
    onSuccess: async () => {
      toast({ title: "Task updated", variant: "success" });
      await invalidate();
    },
    onError: (error) => toast({ title: "Could not update task", description: errorMessage(error), variant: "error" }),
  });

  const detail = detailQuery.data;
  const finding = detail?.finding;
  const members = membersQuery.data ?? [];
  const canWrite = can("finding:write");

  const openEdit = () => {
    if (!finding) return;
    setEditForm({
      status: finding.status,
      severity: finding.severity,
      assignee_id: finding.assignee_id ?? "",
      due_date: isoToDate(finding.due_date),
      recommendation: finding.recommendation ?? "",
      remediation_notes: finding.remediation_notes ?? "",
    });
    setEditError(null);
    setEditOpen(true);
  };

  return (
    <>
      <Modal
        open={Boolean(findingId)}
        onClose={onClose}
        title={finding?.title ?? "Finding detail"}
        description={finding ? `${titleize(finding.finding_type)} · ${finding.confidence} confidence · discovered ${relativeTime(finding.discovered_at)}` : undefined}
        size="xl"
        footer={
          <>
            <Button variant="ghost" size="sm" onClick={onClose}>Close</Button>
            {canWrite && finding ? (
              <Button size="sm" onClick={openEdit}>
                <Pencil aria-hidden="true" className="h-4 w-4" /> Update finding
              </Button>
            ) : null}
          </>
        }
      >
        {detailQuery.isLoading ? (
          <div className="space-y-3"><Skeleton className="h-8 w-64" /><Skeleton className="h-40" /></div>
        ) : detailQuery.isError ? (
          <ErrorState title="Could not load finding" message={errorMessage(detailQuery.error)} onRetry={() => void detailQuery.refetch()} />
        ) : !finding ? null : (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <SeverityBadge severity={finding.severity} />
              <RiskBadge score={finding.risk_score} />
              <StatusBadge status={finding.status} />
              <CvssBadge score={finding.cvss_base_score} />
              {finding.sla_breached ? <Badge tone="critical">SLA breached</Badge> : null}
              <Badge tone={finding.confidence === "confirmed" ? "low" : "medium"}>{titleize(finding.confidence)}</Badge>
              <Link to={`/assets/${finding.asset_id}`} className="text-xs font-medium text-brand-400 hover:text-brand-300" onClick={onClose}>
                {finding.asset_name ?? "Linked asset"}
              </Link>
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-md bg-surface-raised/60 px-3 py-2">
                <p className="text-[11px] text-slate-500">Assignee</p>
                <p className="text-xs text-slate-200">{finding.assignee_name ?? "Unassigned"}</p>
              </div>
              <div className="rounded-md bg-surface-raised/60 px-3 py-2">
                <p className="text-[11px] text-slate-500">Due date</p>
                <p className="text-xs text-slate-200">{finding.due_date ? formatDate(finding.due_date) : "No due date"}</p>
              </div>
              <div className="rounded-md bg-surface-raised/60 px-3 py-2">
                <p className="text-[11px] text-slate-500">Exposure / impact</p>
                <p className="text-xs text-slate-200">{titleize(finding.exposure ?? "unknown")} · {titleize(finding.business_impact ?? "unknown")}</p>
              </div>
            </div>

            <Tabs
              value={tab}
              onValueChange={setTab}
              items={[
                { value: "details", label: "Details", content: null },
                { value: "remediation", label: "Remediation", content: null },
                { value: "tasks", label: `Tasks (${detail.tasks.length})`, content: null },
              ]}
            />

            {tab === "details" ? (
              <div className="space-y-4">
                <section>
                  <h3 className="text-xs font-medium uppercase tracking-wide text-slate-500">Description</h3>
                  <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed text-slate-300">{finding.description ?? "No description recorded."}</p>
                </section>
                {finding.evidence ? (
                  <section>
                    <h3 className="text-xs font-medium uppercase tracking-wide text-slate-500">Evidence</h3>
                    <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap rounded-md bg-surface-raised px-3 py-2 text-xs text-slate-400">{finding.evidence}</pre>
                  </section>
                ) : null}
                <section>
                  <h3 className="text-xs font-medium uppercase tracking-wide text-slate-500">Why this score</h3>
                  {Object.keys(finding.score_factors).length === 0 ? (
                    <p className="mt-1 text-xs text-slate-500">No factor breakdown recorded.</p>
                  ) : (
                    <ul className="mt-1 space-y-1.5">
                      {Object.entries(finding.score_factors).map(([key, value]) => (
                        <li key={key} className="flex items-center justify-between gap-3 rounded bg-surface-raised/50 px-2.5 py-1.5 text-xs">
                          <span className="text-slate-400">{titleize(key)}</span>
                          <span className="num text-slate-200">{typeof value === "number" ? value.toFixed(2) : String(value)}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
                <p className="text-[11px] text-slate-500">
                  Source {titleize(finding.source)} · discovered {relativeTime(finding.discovered_at)}
                  {finding.last_verified_at ? ` · last verified ${relativeTime(finding.last_verified_at)}` : ""}
                </p>
              </div>
            ) : null}

            {tab === "remediation" ? (
              <div className="space-y-4">
                <section>
                  <h3 className="text-xs font-medium uppercase tracking-wide text-slate-500">Recommendation</h3>
                  <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed text-slate-300">{finding.recommendation ?? "No recommendation recorded yet."}</p>
                </section>
                <section>
                  <h3 className="text-xs font-medium uppercase tracking-wide text-slate-500">Remediation notes</h3>
                  <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed text-slate-300">{finding.remediation_notes ?? "No remediation notes yet."}</p>
                </section>
                {canWrite ? (
                  <div>
                    <label htmlFor="finding-note" className="text-xs font-medium text-slate-300">Add a note</label>
                    <textarea
                      id="finding-note"
                      value={note}
                      onChange={(event) => setNote(event.target.value)}
                      rows={3}
                      maxLength={4000}
                      className="mt-1 w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                      placeholder="What was checked, who was contacted, what changed…"
                    />
                    <Button
                      size="sm"
                      className="mt-2"
                      disabled={!note.trim() || noteMutation.isPending}
                      onClick={() => noteMutation.mutate()}
                    >
                      <MessageSquarePlus aria-hidden="true" className="h-4 w-4" />
                      {noteMutation.isPending ? "Adding…" : "Add note"}
                    </Button>
                  </div>
                ) : (
                  <p className="text-xs text-slate-500">Your role can read this finding but not change remediation notes.</p>
                )}
              </div>
            ) : null}

            {tab === "tasks" ? (
              <div className="space-y-4">
                {detail.tasks.length === 0 ? (
                  <EmptyState icon={ListChecks} title="No remediation tasks" description="Break the fix into assigned, trackable steps." className="py-6" />
                ) : (
                  <ul className="space-y-2">
                    {detail.tasks.map((task) => (
                      <li key={task.id} className="rounded-md border border-border bg-surface-raised/40 px-3 py-2.5">
                        <div className="flex flex-wrap items-start justify-between gap-2">
                          <div className="min-w-0">
                            <p className="text-sm text-slate-200">{task.title}</p>
                            <p className="text-[11px] text-slate-500">
                              {titleize(task.priority)} priority · {task.assignee_name ?? "Unassigned"}
                              {task.due_date ? ` · due ${formatDate(task.due_date)}` : ""}
                            </p>
                          </div>
                          {canWrite ? (
                            <Select
                              aria-label={`Status for ${task.title}`}
                              value={task.status}
                              onChange={(event) => taskStatusMutation.mutate({ taskId: task.id, status: event.target.value })}
                              className="w-36"
                            >
                              {TASK_STATUSES.map((status) => <option key={status} value={status}>{titleize(status)}</option>)}
                            </Select>
                          ) : (
                            <StatusBadge status={task.status} />
                          )}
                        </div>
                        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-surface">
                          <div className="h-full rounded-full bg-brand-500" style={{ width: `${task.progress_percent}%` }} />
                        </div>
                      </li>
                    ))}
                  </ul>
                )}

                {canWrite ? (
                  <div className="rounded-md border border-border p-3">
                    <h3 className="text-xs font-medium text-slate-300">New remediation task</h3>
                    <div className="mt-2 grid gap-2 sm:grid-cols-2">
                      <Input
                        aria-label="Task title"
                        value={taskForm.title}
                        onChange={(event) => setTaskForm((current) => ({ ...current, title: event.target.value }))}
                        placeholder="Task title"
                      />
                      <Select
                        aria-label="Task priority"
                        value={taskForm.priority}
                        onChange={(event) => setTaskForm((current) => ({ ...current, priority: event.target.value }))}
                      >
                        {TASK_PRIORITIES.map((priority) => <option key={priority} value={priority}>{titleize(priority)}</option>)}
                      </Select>
                      {can("user:read") ? (
                        <Select
                          aria-label="Task assignee"
                          value={taskForm.assignee_id}
                          onChange={(event) => setTaskForm((current) => ({ ...current, assignee_id: event.target.value }))}
                        >
                          <option value="">Unassigned</option>
                          {members.map((member) => <option key={member.user_id} value={member.user_id}>{member.full_name}</option>)}
                        </Select>
                      ) : null}
                      <Input
                        aria-label="Task due date"
                        type="date"
                        value={taskForm.due_date}
                        onChange={(event) => setTaskForm((current) => ({ ...current, due_date: event.target.value }))}
                      />
                    </div>
                    <Button
                      size="sm"
                      className="mt-2"
                      disabled={taskForm.title.trim().length < 2 || taskMutation.isPending}
                      onClick={() => taskMutation.mutate()}
                    >
                      <ListChecks aria-hidden="true" className="h-4 w-4" />
                      {taskMutation.isPending ? "Creating…" : "Create task"}
                    </Button>
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        )}
      </Modal>

      <Modal
        open={editOpen && Boolean(editForm)}
        onClose={() => setEditOpen(false)}
        title="Update finding"
        description="Status changes recalculate asset and company risk. Confirmed vs potential remains a separate confidence field."
        size="lg"
        footer={
          <>
            <Button variant="ghost" size="sm" onClick={() => setEditOpen(false)} disabled={updateMutation.isPending}>Cancel</Button>
            <Button
              size="sm"
              disabled={updateMutation.isPending}
              onClick={() => {
                if (!editForm) return;
                setEditError(null);
                updateMutation.mutate({
                  status: editForm.status,
                  severity: editForm.severity,
                  assignee_id: editForm.assignee_id || null,
                  due_date: toIsoDate(editForm.due_date),
                  recommendation: editForm.recommendation.trim() || null,
                  remediation_notes: editForm.remediation_notes.trim() || null,
                });
              }}
            >
              {updateMutation.isPending ? "Saving…" : "Save changes"}
            </Button>
          </>
        }
      >
        {editForm ? (
          <div className="space-y-4">
            {editError ? (
              <p role="alert" className="rounded-md border border-critical/30 bg-critical/10 px-3 py-2 text-xs text-critical">{editError}</p>
            ) : null}
            <div className="grid gap-4 sm:grid-cols-2">
              <Select label="Status" value={editForm.status} onChange={(event) => setEditForm({ ...editForm, status: event.target.value })}>
                {["open", "triaged", "assigned", "in_progress", "remediated", "accepted_risk", "false_positive", "duplicate"].map((status) => (
                  <option key={status} value={status}>{titleize(status)}</option>
                ))}
              </Select>
              <Select label="Severity" value={editForm.severity} onChange={(event) => setEditForm({ ...editForm, severity: event.target.value })}>
                {SEVERITIES.map((severity) => <option key={severity} value={severity}>{titleize(severity)}</option>)}
              </Select>
              {can("user:read") ? (
                <Select label="Assignee" value={editForm.assignee_id} onChange={(event) => setEditForm({ ...editForm, assignee_id: event.target.value })}>
                  <option value="">Unassigned</option>
                  {members.map((member) => <option key={member.user_id} value={member.user_id}>{member.full_name}</option>)}
                </Select>
              ) : null}
              <Input label="Due date" type="date" value={editForm.due_date} onChange={(event) => setEditForm({ ...editForm, due_date: event.target.value })} />
            </div>
            <div>
              <label htmlFor="finding-recommendation" className="text-xs font-medium text-slate-300">Recommendation</label>
              <textarea
                id="finding-recommendation"
                rows={3}
                value={editForm.recommendation}
                onChange={(event) => setEditForm({ ...editForm, recommendation: event.target.value })}
                className="mt-1 w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-slate-200 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
              />
            </div>
            <div>
              <label htmlFor="finding-notes" className="text-xs font-medium text-slate-300">Remediation notes</label>
              <textarea
                id="finding-notes"
                rows={3}
                value={editForm.remediation_notes}
                onChange={(event) => setEditForm({ ...editForm, remediation_notes: event.target.value })}
                className="mt-1 w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-slate-200 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
              />
            </div>
          </div>
        ) : null}
      </Modal>
    </>
  );
}

export function FindingsPage() {
  const { selectedCompanyId, can, enums } = useAuth();
  const { toast } = useToast();
  const [searchParams, setSearchParams] = useSearchParams();
  const focus = searchParams.get("focus");
  const [search, setSearch] = useState("");
  const [severity, setSeverity] = useState("");
  const [status, setStatus] = useState("");
  const [findingType, setFindingType] = useState("");
  const [confidence, setConfidence] = useState("");
  const [openOnly, setOpenOnly] = useState("true");
  const [slaBreached, setSlaBreached] = useState("");
  const [minRisk, setMinRisk] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize] = useState(25);
  const [sort, setSort] = useState("risk_score");
  const [order, setOrder] = useState<"asc" | "desc">("desc");
  const [exporting, setExporting] = useState(false);

  const filters = {
    q: search.trim() || undefined,
    severity: severity ? [severity] : undefined,
    status: status || undefined,
    finding_type: findingType || undefined,
    confidence: confidence || undefined,
    open_only: openOnly === "true" ? true : undefined,
    sla_breached: slaBreached === "" ? undefined : slaBreached === "true",
    min_risk: minRisk ? Number(minRisk) : undefined,
  };

  const query = useQuery({
    queryKey: ["findings", selectedCompanyId, filters, page, pageSize, sort, order],
    queryFn: () =>
      apiRequest<Page<Finding>>(`/companies/${selectedCompanyId}/findings`, {
        params: { ...filters, page, page_size: pageSize, sort, order },
      }),
    enabled: Boolean(selectedCompanyId),
    placeholderData: (previous) => previous,
  });

  const data = query.data;
  const items = data?.items ?? [];
  const setFocus = (id: string | null) => {
    const next = new URLSearchParams(searchParams);
    if (id) next.set("focus", id);
    else next.delete("focus");
    setSearchParams(next, { replace: true });
  };
  const reset = () => {
    setSearch("");
    setSeverity("");
    setStatus("");
    setFindingType("");
    setConfidence("");
    setOpenOnly("true");
    setSlaBreached("");
    setMinRisk("");
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
  const exportCsv = async () => {
    setExporting(true);
    try {
      const { blob, filename } = await downloadFile(`/companies/${selectedCompanyId}/findings/export`, filters);
      saveBlob(blob, filename ?? "findings.csv");
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
        title="Findings & remediation"
        description={
          data
            ? `${formatNumber(data.total)} finding(s) match the current filters. Risk scores blend severity, confidence, exposure and business impact.`
            : "Open issues across the tenant with an explainable risk score and remediation workflow."
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
          <p className="text-xs uppercase tracking-wide text-slate-500">Matching findings</p>
          <p className="mt-1 text-2xl font-semibold text-slate-50">{data ? formatNumber(data.total) : "—"}</p>
        </div>
        <div className="metric-card">
          <p className="text-xs uppercase tracking-wide text-slate-500">Critical on page</p>
          <p className="mt-1 text-2xl font-semibold text-critical">{items.filter((item) => item.severity === "critical").length}</p>
        </div>
        <div className="metric-card">
          <p className="text-xs uppercase tracking-wide text-slate-500">High on page</p>
          <p className="mt-1 text-2xl font-semibold text-high">{items.filter((item) => item.severity === "high").length}</p>
        </div>
        <div className="metric-card">
          <p className="text-xs uppercase tracking-wide text-slate-500">SLA breached on page</p>
          <p className="mt-1 text-2xl font-semibold text-medium">{items.filter((item) => item.sla_breached).length}</p>
        </div>
      </div>

      <Card>
        <CardContent className="space-y-3">
          <div className="flex flex-col gap-2 xl:flex-row xl:flex-wrap xl:items-center">
            <SearchInput value={search} onChange={(value) => { setSearch(value); setPage(1); }} placeholder="Search title, asset or evidence" />
            <Select aria-label="Severity" value={severity} onChange={(event) => { setSeverity(event.target.value); setPage(1); }} className="xl:w-36">
              <option value="">Any severity</option>
              {SEVERITIES.map((value) => <option key={value} value={value}>{titleize(value)}</option>)}
            </Select>
            <Select aria-label="Status" value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }} className="xl:w-40">
              <option value="">Any status</option>
              {(enums?.finding_statuses ?? []).map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </Select>
            <Select aria-label="Finding type" value={findingType} onChange={(event) => { setFindingType(event.target.value); setPage(1); }} className="xl:w-44">
              <option value="">Any type</option>
              {(enums?.finding_types ?? []).map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </Select>
            <Select aria-label="Confidence" value={confidence} onChange={(event) => { setConfidence(event.target.value); setPage(1); }} className="xl:w-40">
              <option value="">Any confidence</option>
              {CONFIDENCE.map((value) => <option key={value} value={value}>{titleize(value)}</option>)}
            </Select>
            <Select aria-label="Open only" value={openOnly} onChange={(event) => { setOpenOnly(event.target.value); setPage(1); }} className="xl:w-40">
              <option value="true">Open only</option>
              <option value="false">All statuses</option>
            </Select>
            <Select aria-label="SLA breached" value={slaBreached} onChange={(event) => { setSlaBreached(event.target.value); setPage(1); }} className="xl:w-40">
              <option value="">SLA: any</option>
              <option value="true">SLA breached</option>
              <option value="false">Within SLA</option>
            </Select>
            <Select aria-label="Minimum risk" value={minRisk} onChange={(event) => { setMinRisk(event.target.value); setPage(1); }} className="xl:w-40">
              <option value="">Any risk</option>
              <option value="8.5">Risk ≥ 8.5</option>
              <option value="6.5">Risk ≥ 6.5</option>
              <option value="4">Risk ≥ 4.0</option>
            </Select>
            {search || severity || status || findingType || confidence || slaBreached || minRisk || openOnly !== "true" ? (
              <Button variant="ghost" size="sm" onClick={reset}><RotateCcw aria-hidden="true" className="h-3.5 w-3.5" /> Reset</Button>
            ) : null}
          </div>

          {query.isLoading ? (
            <TableLoading columns={8} />
          ) : query.isError ? (
            <ErrorState title="Could not load findings" message={errorMessage(query.error)} onRetry={() => void query.refetch()} />
          ) : items.length === 0 ? (
            <EmptyState
              icon={ShieldCheck}
              title={openOnly === "true" ? "No open findings" : "No findings match these filters"}
              description={
                openOnly === "true"
                  ? "Nothing currently needs remediation, or findings were filtered out by the other criteria."
                  : "Adjust or clear the filters to widen the search."
              }
              action={<Button variant="ghost" size="sm" onClick={reset}>Clear filters</Button>}
            />
          ) : (
            <>
              <div className="overflow-x-auto rounded-md border border-border">
                <Table>
                  <THead>
                    <Tr>
                      <Th>Finding</Th>
                      <Th sortable sortDirection={sort === "severity" ? order : undefined} onSort={() => toggleSort("severity")}>Severity</Th>
                      <Th sortable align="right" sortDirection={sort === "risk_score" ? order : undefined} onSort={() => toggleSort("risk_score")}>Risk</Th>
                      <Th className="hidden lg:table-cell">Confidence</Th>
                      <Th sortable sortDirection={sort === "status" ? order : undefined} onSort={() => toggleSort("status")}>Status</Th>
                      <Th className="hidden xl:table-cell">Assignee</Th>
                      <Th sortable className="hidden lg:table-cell" sortDirection={sort === "due_date" ? order : undefined} onSort={() => toggleSort("due_date")}>Due / SLA</Th>
                      <Th className="hidden md:table-cell">Discovered</Th>
                      <Th align="right">Tasks</Th>
                    </Tr>
                  </THead>
                  <TBody>
                    {items.map((finding) => (
                      <Tr key={finding.id} className="cursor-pointer" onClick={() => setFocus(finding.id)}>
                        <Td>
                          <button
                            type="button"
                            onClick={(event) => { event.stopPropagation(); setFocus(finding.id); }}
                            className="block max-w-[24rem] truncate text-left font-medium text-slate-200 hover:text-brand-400"
                            title={finding.title}
                          >
                            {finding.title}
                          </button>
                          <p className="mt-0.5 truncate text-[11px] text-slate-500">
                            {titleize(finding.finding_type)} ·{" "}
                            {finding.asset_id ? (
                              <Link to={`/assets/${finding.asset_id}`} onClick={(event) => event.stopPropagation()} className="text-brand-400/80 hover:text-brand-300">
                                {finding.asset_name ?? "asset"}
                              </Link>
                            ) : "unlinked"}
                          </p>
                        </Td>
                        <Td><SeverityBadge severity={finding.severity} /></Td>
                        <Td align="right"><RiskBadge score={finding.risk_score} /></Td>
                        <Td className="hidden lg:table-cell"><Badge tone={finding.confidence === "confirmed" ? "low" : "medium"}>{titleize(finding.confidence)}</Badge></Td>
                        <Td><StatusBadge status={finding.status} /></Td>
                        <Td className="hidden xl:table-cell"><span className="text-xs text-slate-300">{finding.assignee_name ?? "Unassigned"}</span></Td>
                        <Td className="hidden lg:table-cell">
                          <p className="text-xs text-slate-400">{finding.due_date ? formatDate(finding.due_date) : "No due date"}</p>
                          {finding.sla_breached ? <Badge tone="critical">Breached</Badge> : <Badge tone="low">Within SLA</Badge>}
                        </Td>
                        <Td className="hidden md:table-cell"><span className="text-xs text-slate-500">{relativeTime(finding.discovered_at)}</span></Td>
                        <Td align="right"><span className="num text-xs text-slate-400">{finding.task_count}</span></Td>
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
        <FileText aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        “Confirmed” means the probe produced direct evidence; “potential” means it was inferred. Neither is a substitute for human validation.
      </p>

      <FindingDetailModal findingId={focus} onClose={() => setFocus(null)} />
    </div>
  );
}

export default FindingsPage;
