import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Building2,
  Download,
  FileSpreadsheet,
  FileText,
  History,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";

import { PageHeader } from "@/components/common/PageHeader";
import { RiskBadge } from "@/components/common/Badges";
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
  Pagination,
  Skeleton,
  Table,
  TBody,
  Td,
  Th,
  THead,
  Tr,
  useToast,
} from "@/components/ui";
import {
  apiRequest,
  downloadPost,
  errorMessage,
  saveBlob,
} from "@/lib/api";
import type { Dashboard, Page, ReportRecord, RiskSummary } from "@/lib/apiTypes";
import { severityLabel, titleize } from "@/lib/labels";
import { formatDateTime, formatNumber, relativeTime } from "@/lib/utils";
import { useAuth } from "@/context/AuthProvider";

const TEMPLATES = [
  {
    value: "asset_inventory",
    label: "Asset inventory",
    description: "Every asset with type, status, criticality, exposure, owner, source and risk score.",
  },
  {
    value: "findings",
    label: "Findings",
    description: "Findings with severity, confidence, SLA state, assignee and discovery source.",
  },
  {
    value: "vulnerabilities",
    label: "Vulnerabilities",
    description: "CVE records with CVSS, confidence, affected versions and remediation state.",
  },
  {
    value: "certificates",
    label: "Certificates",
    description: "Certificate hosts, issuers, validity window, days remaining and source.",
  },
] as const;

export function ReportsPage() {
  const { selectedCompanyId, user, can } = useAuth();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);

  const reportsQuery = useQuery({
    queryKey: ["reports", selectedCompanyId, page, pageSize],
    queryFn: () =>
      apiRequest<Page<ReportRecord>>(`/companies/${selectedCompanyId}/reports`, {
        params: { page, page_size: pageSize },
      }),
    enabled: Boolean(selectedCompanyId),
    placeholderData: (previous) => previous,
  });

  const riskQuery = useQuery({
    queryKey: ["company-risk", selectedCompanyId],
    queryFn: () =>
      apiRequest<RiskSummary>(`/companies/${selectedCompanyId}/risk`),
    enabled: Boolean(selectedCompanyId),
  });

  const isSuperAdmin = user?.role_code === "super_admin";
  const comparisonQuery = useQuery({
    queryKey: ["dashboard", selectedCompanyId],
    queryFn: () =>
      apiRequest<Dashboard>(`/companies/${selectedCompanyId}/dashboard`),
    enabled: Boolean(selectedCompanyId) && isSuperAdmin,
    staleTime: 60_000,
  });

  const generateMutation = useMutation({
    mutationFn: async (template: string) => {
      const file = await downloadPost(
        `/companies/${selectedCompanyId}/reports`,
        { template, format: "csv" },
      );
      saveBlob(
        file.blob,
        file.filename ?? `${template}-${new Date().toISOString().slice(0, 10)}.csv`,
      );
      return template;
    },
    onSuccess: async (template) => {
      toast({
        title: `${titleize(template)} CSV downloaded`,
        description: "The export is recorded in the report catalogue below.",
        variant: "success",
      });
      await queryClient.invalidateQueries({ queryKey: ["reports"] });
    },
    onError: (error) =>
      toast({
        title: "Could not generate report",
        description: errorMessage(error),
        variant: "error",
      }),
  });

  const reports = reportsQuery.data;
  const risk = riskQuery.data;
  const comparison = comparisonQuery.data?.companies ?? [];
  const latestByTemplate = new Map<string, ReportRecord>();
  for (const report of reports?.items ?? []) {
    if (!latestByTemplate.has(report.template)) {
      latestByTemplate.set(report.template, report);
    }
  }

  if (!selectedCompanyId) return null;

  return (
    <div>
      <PageHeader
        title="Reports & exports"
        description="Generate scoped CSV exports and review what was exported. Every run is recorded in the catalogue with its row count and requesting user."
      />

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Generate a report</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid gap-3 sm:grid-cols-2">
              {TEMPLATES.map((template) => {
                const latest = latestByTemplate.get(template.value);
                const generating =
                  generateMutation.isPending &&
                  generateMutation.variables === template.value;
                return (
                  <div
                    key={template.value}
                    className="flex flex-col gap-2 rounded-md border border-border bg-surface-raised/40 p-3"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <FileSpreadsheet aria-hidden="true" className="h-4 w-4 text-brand-400" />
                        <p className="text-sm font-medium text-slate-200">{template.label}</p>
                      </div>
                      <Badge tone="neutral">CSV</Badge>
                    </div>
                    <p className="flex-1 text-xs text-slate-500">{template.description}</p>
                    {latest ? (
                      <p className="text-[11px] text-slate-600">
                        Last exported {relativeTime(latest.generated_at)} · {formatNumber(latest.row_count)} rows
                      </p>
                    ) : (
                      <p className="text-[11px] text-slate-600">Not exported yet</p>
                    )}
                    <div className="flex items-center gap-2">
                      <Button
                        size="sm"
                        onClick={() => generateMutation.mutate(template.value)}
                        loading={generating}
                        disabled={!can("report:export")}
                      >
                        <Download aria-hidden="true" className="h-3.5 w-3.5" />
                        Download CSV
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled
                        title="PDF export is not implemented. The API rejects PDF requests rather than returning a mislabelled file."
                      >
                        PDF (not implemented)
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
            <p className="mt-3 text-[11px] text-slate-500">
              Exports are generated on demand and streamed to your browser. The catalogue records
              the run but does not retain the file itself — re-export for a fresh copy.
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Company risk snapshot</CardTitle>
          </CardHeader>
          <CardContent>
            {riskQuery.isLoading ? (
              <div className="space-y-2">
                <Skeleton className="h-16" />
                <Skeleton className="h-24" />
              </div>
            ) : riskQuery.isError ? (
              <ErrorState
                title="Could not load risk snapshot"
                message={errorMessage(riskQuery.error)}
                onRetry={() => void riskQuery.refetch()}
              />
            ) : risk ? (
              <div className="space-y-3">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-[11px] uppercase tracking-wide text-slate-500">Risk score</p>
                    <p className="num text-3xl font-semibold text-slate-50">{risk.score.toFixed(1)}</p>
                    <p className="text-xs text-slate-400">{titleize(risk.classification)}</p>
                  </div>
                  <RiskBadge score={risk.score} classification={risk.classification} />
                </div>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div className="rounded-md bg-surface-raised/60 px-2 py-1.5">
                    <p className="text-slate-500">Open findings</p>
                    <p className="num text-slate-200">{formatNumber(risk.open_findings)}</p>
                  </div>
                  <div className="rounded-md bg-surface-raised/60 px-2 py-1.5">
                    <p className="text-slate-500">Model</p>
                    <p className="num text-slate-200">{risk.model_version}</p>
                  </div>
                  <div className="rounded-md bg-surface-raised/60 px-2 py-1.5">
                    <p className="text-slate-500">Previous</p>
                    <p className="num text-slate-200">{risk.previous_score === null ? "—" : risk.previous_score.toFixed(1)}</p>
                  </div>
                  <div className="rounded-md bg-surface-raised/60 px-2 py-1.5">
                    <p className="text-slate-500">Delta</p>
                    <p className={`num ${risk.delta !== null && risk.delta > 0 ? "text-high" : "text-slate-200"}`}>
                      {risk.delta === null ? "—" : `${risk.delta > 0 ? "+" : ""}${risk.delta.toFixed(1)}`}
                    </p>
                  </div>
                </div>
                <div className="grid grid-cols-5 gap-1 text-center">
                  {(["critical", "high", "medium", "low", "informational"] as const).map((severity) => (
                    <div key={severity} className="rounded bg-surface-raised/60 py-1">
                      <p className="text-[10px] text-slate-500">{severityLabel(severity).slice(0, 4)}</p>
                      <p className="num text-xs text-slate-200">{risk.severity_counts[severity] ?? 0}</p>
                    </div>
                  ))}
                </div>
                {risk.factors.length > 0 ? (
                  <div className="space-y-1.5">
                    <p className="text-[11px] uppercase tracking-wide text-slate-500">Top factors</p>
                    {risk.factors
                      .slice()
                      .sort((a, b) => b.contribution - a.contribution)
                      .slice(0, 4)
                      .map((factor) => (
                        <div key={factor.key} className="flex items-center justify-between gap-2 text-[11px]">
                          <span className="truncate text-slate-400">{factor.label}</span>
                          <span className="num shrink-0 text-slate-300">{factor.contribution.toFixed(2)}</span>
                        </div>
                      ))}
                  </div>
                ) : null}
                <p className="text-[11px] text-slate-500">
                  {risk.computed_at
                    ? `Computed ${formatDateTime(risk.computed_at)}.`
                    : risk.note ?? "No stored snapshot; computed on request."}
                </p>
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader className="flex flex-row items-center justify-between gap-2">
            <CardTitle>Report catalogue</CardTitle>
            <History aria-hidden="true" className="h-4 w-4 text-slate-500" />
          </CardHeader>
          <CardContent>
            {reportsQuery.isLoading ? (
              <TableLoading columns={6} rows={4} />
            ) : reportsQuery.isError ? (
              <ErrorState
                title="Could not load reports"
                message={errorMessage(reportsQuery.error)}
                onRetry={() => void reportsQuery.refetch()}
              />
            ) : (reports?.items.length ?? 0) === 0 ? (
              <EmptyState
                icon={FileText}
                title="No reports generated yet"
                description="Generate a CSV above. Each export is recorded here with its requester and row count."
              />
            ) : (
              <>
                <div className="overflow-x-auto rounded-md border border-border">
                  <Table>
                    <THead>
                      <Tr>
                        <Th>Report</Th>
                        <Th>Template</Th>
                        <Th>Format</Th>
                        <Th>Rows</Th>
                        <Th className="hidden lg:table-cell">Generated by</Th>
                        <Th>Generated</Th>
                      </Tr>
                    </THead>
                    <TBody>
                      {reports?.items.map((report) => (
                        <Tr key={report.id}>
                          <Td>
                            <p className="max-w-[16rem] truncate text-xs font-medium text-slate-200">{report.name}</p>
                            <p className="text-[11px] text-slate-500">{report.artifact_filename ?? "No artifact filename"}</p>
                          </Td>
                          <Td><span className="text-xs text-slate-400">{titleize(report.template)}</span></Td>
                          <Td><Badge tone="neutral">{report.format.toUpperCase()}</Badge></Td>
                          <Td><span className="num text-xs text-slate-300">{formatNumber(report.row_count)}</span></Td>
                          <Td className="hidden lg:table-cell"><span className="text-xs text-slate-400">{report.generated_by_email ?? "—"}</span></Td>
                          <Td><span className="text-xs text-slate-400" title={formatDateTime(report.generated_at)}>{relativeTime(report.generated_at)}</span></Td>
                        </Tr>
                      ))}
                    </TBody>
                  </Table>
                </div>
                <Pagination
                  className="mt-3"
                  page={reports?.page ?? page}
                  total={reports?.total}
                  pageSize={reports?.page_size ?? pageSize}
                  onPageChange={setPage}
                />
              </>
            )}
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Export integrity</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-xs text-slate-400">
              <p className="flex gap-2">
                <ShieldCheck aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-400" />
                Exports are tenant-scoped and require the <span className="text-slate-200">report:export</span> permission.
              </p>
              <p className="flex gap-2">
                <TriangleAlert aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0 text-medium" />
                PDF export is deliberately rejected by the backend. No document is produced that claims to be a PDF.
              </p>
              <p className="flex gap-2">
                <FileText aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-500" />
                Report rows reflect stored records, including rows explicitly labelled as sample data.
              </p>
            </CardContent>
          </Card>

          {isSuperAdmin ? (
            <Card>
              <CardHeader className="flex flex-row items-center gap-2">
                <Building2 aria-hidden="true" className="h-4 w-4 text-slate-500" />
                <CardTitle>Cross-company comparison</CardTitle>
              </CardHeader>
              <CardContent>
                {comparisonQuery.isLoading ? (
                  <Skeleton className="h-24" />
                ) : comparisonQuery.isError ? (
                  <p className="text-xs text-slate-500">{errorMessage(comparisonQuery.error)}</p>
                ) : comparison.length <= 1 ? (
                  <p className="text-xs text-slate-500">Comparison appears when more than one company is authorized.</p>
                ) : (
                  <div className="space-y-2">
                    {comparison
                      .slice()
                      .sort((a, b) => b.risk_score - a.risk_score)
                      .map((company) => (
                        <div key={company.company_id} className="flex items-center justify-between gap-2 text-xs">
                          <span className="truncate text-slate-300">{company.name}</span>
                          <span className="flex shrink-0 items-center gap-2">
                            <span className="text-slate-500">{formatNumber(company.critical_findings)} critical</span>
                            <RiskBadge score={company.risk_score} />
                          </span>
                        </div>
                      ))}
                  </div>
                )}
                <p className="mt-3 text-[11px] text-slate-500">
                  Visible only to platform administrators; tenant users see only their own company.
                </p>
              </CardContent>
            </Card>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export default ReportsPage;
