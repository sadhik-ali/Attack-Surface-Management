import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  Boxes,
  FileText,
  Globe2,
  Info,
  RefreshCw,
  ScanLine,
  ServerCog,
  ShieldAlert,
  ShieldCheck,
  ShieldQuestion,
} from "lucide-react";
import {
  Area,
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip as ChartTooltip,
  XAxis,
  YAxis,
} from "recharts";

import { PageHeader } from "@/components/common/PageHeader";
import { StatCard } from "@/components/common/StatCard";
import { RiskBadge, SeverityBadge, StatusBadge } from "@/components/common/Badges";
import { Button, Card, CardContent, CardHeader, CardTitle, EmptyState, ErrorState, Skeleton } from "@/components/ui";
import { apiRequest, errorMessage } from "@/lib/api";
import type { Dashboard, SeverityCounts } from "@/lib/apiTypes";
import { CHART_AXIS, CHART_GRID, CHART_PALETTE, RISK_COLORS, TOOLTIP_STYLE, shortDate } from "@/lib/charts";
import { riskTextClass, titleize } from "@/lib/labels";
import { formatDateTime, formatNumber, relativeTime } from "@/lib/utils";
import { useAuth } from "@/context/AuthProvider";

const SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"] as const;

function severityCount(counts: SeverityCounts, key: string): number {
  return counts[key as keyof SeverityCounts] ?? 0;
}

function RiskRing({ score, classification }: { score: number; classification: string }) {
  const radius = 46;
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.max(0, Math.min(score, 10));
  const filled = (clamped / 10) * circumference;
  const color = RISK_COLORS[classification.toLowerCase()] ?? RISK_COLORS.info;
  return (
    <div className="relative h-32 w-32 shrink-0">
      <svg viewBox="0 0 120 120" className="h-full w-full -rotate-90" role="img" aria-label={`Risk score ${score.toFixed(1)} of 10, ${classification}`}>
        <circle cx="60" cy="60" r={radius} fill="none" stroke="#1E2A3C" strokeWidth="10" />
        <circle
          cx="60"
          cy="60"
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={`${filled} ${circumference - filled}`}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="num text-3xl font-semibold text-slate-50">{score.toFixed(1)}</span>
        <span className={`text-[11px] font-medium uppercase tracking-wide ${riskTextClass(classification, score)}`}>
          {titleize(classification)}
        </span>
        <span className="text-[10px] text-slate-500">out of 10</span>
      </div>
    </div>
  );
}

function SourceNote({ note }: { note: string }) {
  return (
    <div className="mb-5 flex items-start gap-2.5 rounded-lg border border-brand-500/20 bg-brand-500/5 px-3.5 py-2.5 text-xs text-slate-400">
      <Info aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-brand-400" />
      <p className="leading-relaxed">{note}</p>
    </div>
  );
}

function TrendChart({ data }: { data: Dashboard["trend"] }) {
  const points = useMemo(
    () =>
      data.map((point) => ({
        ...point,
        label: shortDate(point.date),
        risk_plot: Number(point.risk_score.toFixed(2)),
      })),
    [data],
  );
  if (points.length === 0) {
    return (
      <EmptyState
        icon={Activity}
        title="No trend history yet"
        description="Trend data appears after the first daily risk snapshot."
        className="py-12"
      />
    );
  }
  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={points} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
          <CartesianGrid stroke={CHART_GRID} strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="label" tick={{ fill: CHART_AXIS, fontSize: 11 }} tickLine={false} axisLine={false} minTickGap={24} />
          <YAxis yAxisId="risk" domain={[0, 10]} tick={{ fill: CHART_AXIS, fontSize: 11 }} tickLine={false} axisLine={false} />
          <YAxis yAxisId="count" orientation="right" allowDecimals={false} tick={{ fill: CHART_AXIS, fontSize: 11 }} tickLine={false} axisLine={false} />
          <ChartTooltip contentStyle={TOOLTIP_STYLE} labelStyle={{ color: "#94A3B8" }} />
          <Legend wrapperStyle={{ fontSize: 11, color: CHART_AXIS }} />
          <Area
            yAxisId="risk"
            type="monotone"
            dataKey="risk_plot"
            name="Risk score"
            stroke={CHART_PALETTE[0]}
            fill={CHART_PALETTE[0]}
            fillOpacity={0.15}
            strokeWidth={2}
          />
          <Bar yAxisId="count" dataKey="critical" name="Critical findings" fill={RISK_COLORS.critical} radius={[3, 3, 0, 0]} barSize={10} />
          <Bar yAxisId="count" dataKey="high" name="High findings" fill={RISK_COLORS.high} radius={[3, 3, 0, 0]} barSize={10} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

function SeverityBars({
  title,
  counts,
  total,
  href,
}: {
  title: string;
  counts: SeverityCounts;
  total: number;
  href: string;
}) {
  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-medium text-slate-200">{title}</h3>
        <Link to={href} className="inline-flex items-center gap-1 text-xs font-medium text-brand-400 hover:text-brand-300">
          View all <ArrowRight aria-hidden="true" className="h-3 w-3" />
        </Link>
      </div>
      <div className="space-y-2.5">
        {SEVERITY_ORDER.map((severity) => {
          const count = severityCount(counts, severity);
          const width = total > 0 ? Math.round((count / total) * 100) : 0;
          return (
            <div key={severity} className="flex items-center gap-3">
              <span className="w-20 shrink-0">
                <SeverityBadge severity={severity} />
              </span>
              <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-raised">
                <div
                  className="h-full rounded-full"
                  style={{ width: `${width}%`, backgroundColor: RISK_COLORS[severity] ?? CHART_PALETTE[0] }}
                />
              </div>
              <span className="num w-8 text-right text-xs text-slate-300">{count}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function DashboardPage() {
  const { selectedCompanyId, selectedCompany, can } = useAuth();
  const query = useQuery({
    queryKey: ["dashboard", selectedCompanyId],
    queryFn: () => apiRequest<Dashboard>(`/companies/${selectedCompanyId}/dashboard`),
    enabled: Boolean(selectedCompanyId),
    refetchInterval: 60_000,
  });

  if (!selectedCompanyId) return null;
  if (query.isLoading) {
    return (
      <div className="space-y-5">
        <Skeleton className="h-10 w-64" />
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          {Array.from({ length: 5 }).map((_, index) => (
            <Skeleton key={index} className="h-28" />
          ))}
        </div>
        <div className="grid gap-4 lg:grid-cols-3">
          <Skeleton className="h-96 lg:col-span-2" />
          <Skeleton className="h-96" />
        </div>
      </div>
    );
  }
  if (query.isError) {
    return (
      <ErrorState
        title="Dashboard unavailable"
        message={errorMessage(query.error)}
        onRetry={() => void query.refetch()}
      />
    );
  }
  const data = query.data;
  if (!data) return null;

  const metrics = data.metrics;
  const risk = data.risk;
  const reportHref = `/reports?company=${selectedCompanyId}`;
  const findingsTotal = SEVERITY_ORDER.reduce((sum, severity) => sum + severityCount(data.findings_by_severity, severity), 0);
  const vulnerabilitiesTotal = SEVERITY_ORDER.reduce(
    (sum, severity) => sum + severityCount(data.vulnerabilities_by_severity, severity),
    0,
  );
  const assetMix = data.asset_mix.filter((entry) => entry.count > 0);
  const comparison = data.companies.filter((entry) => entry.company_id !== selectedCompanyId);

  return (
    <div>
      <PageHeader
        title="Security dashboard"
        description={
          <span>
            {selectedCompany?.name ?? data.company_name} · posture generated {formatDateTime(data.generated_at)}
            {metrics.last_scan_at ? ` · last discovery run ${relativeTime(metrics.last_scan_at)}` : " · no discovery run yet"}
          </span>
        }
        actions={
          <>
            <Button variant="ghost" size="sm" onClick={() => void query.refetch()} disabled={query.isFetching}>
              <RefreshCw aria-hidden="true" className={`h-4 w-4 ${query.isFetching ? "animate-spin" : ""}`} />
              Refresh
            </Button>
            {can("discovery:run") ? (
              <Link to="/scans">
                <Button size="sm">
                  <ScanLine aria-hidden="true" className="h-4 w-4" />
                  New discovery run
                </Button>
              </Link>
            ) : null}
            {can("report:export") ? (
              <Link to={reportHref}>
                <Button variant="ghost" size="sm">
                  <FileText aria-hidden="true" className="h-4 w-4" />
                  Reports
                </Button>
              </Link>
            ) : null}
          </>
        }
      />

      <SourceNote note={data.data_provenance_note} />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <StatCard
          label="Total assets"
          value={formatNumber(metrics.total_assets)}
          hint={`${formatNumber(metrics.assets_new_7d)} new in the last 7 days`}
          icon={Boxes}
          tone="brand"
        />
        <StatCard
          label="Open findings"
          value={formatNumber(metrics.findings_open)}
          hint={`${severityCount(data.findings_by_severity, "critical")} critical · ${severityCount(data.findings_by_severity, "high")} high`}
          icon={ShieldAlert}
          tone={severityCount(data.findings_by_severity, "critical") > 0 ? "critical" : "high"}
        />
        <StatCard
          label="Certificates at risk"
          value={formatNumber(data.certificate_snapshot.expiring_soon + data.certificate_snapshot.expired)}
          hint={`${data.certificate_snapshot.expired} expired · ${data.certificate_snapshot.expiring_soon} expiring soon`}
          icon={ShieldQuestion}
          tone={data.certificate_snapshot.expired > 0 ? "critical" : "medium"}
        />
        <StatCard
          label="Risky services"
          value={formatNumber(data.service_snapshot.risky)}
          hint={`${data.service_snapshot.unexpected} unexpected · ${data.service_snapshot.management_interfaces} management interfaces`}
          icon={ServerCog}
          tone={data.service_snapshot.risky > 0 ? "high" : "low"}
        />
        <StatCard
          label="New alerts"
          value={formatNumber(metrics.alerts_new)}
          hint={`${formatNumber(metrics.changes_7d)} configuration changes in 7 days`}
          icon={AlertTriangle}
          tone={metrics.alerts_new > 0 ? "medium" : "neutral"}
        />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle>Risk trend</CardTitle>
              <p className="mt-1 text-xs text-slate-500">Daily score plus critical and high findings, last 30 days.</p>
            </div>
            <RiskBadge score={risk.score} classification={risk.classification} />
          </CardHeader>
          <CardContent>
            <TrendChart data={data.trend} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Risk score explained</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-4">
              <RiskRing score={risk.score} classification={risk.classification} />
              <div className="min-w-0 space-y-2">
                {risk.delta !== null ? (
                  <span
                    className={`inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium ${
                      risk.delta > 0
                        ? "bg-critical/10 text-critical"
                        : risk.delta < 0
                          ? "bg-low/10 text-low"
                          : "bg-surface-raised text-slate-400"
                    }`}
                  >
                    {risk.delta > 0 ? (
                      <ArrowUpRight aria-hidden="true" className="h-3.5 w-3.5" />
                    ) : risk.delta < 0 ? (
                      <ArrowDownRight aria-hidden="true" className="h-3.5 w-3.5" />
                    ) : null}
                    {risk.delta === 0 ? "No change" : `${risk.delta > 0 ? "+" : ""}${risk.delta.toFixed(2)}`}
                    {risk.previous_score !== null ? (
                      <span className="font-normal opacity-70">vs {risk.previous_score.toFixed(1)}</span>
                    ) : null}
                  </span>
                ) : null}
                <p className="text-xs leading-relaxed text-slate-400">
                  {risk.driver_summary ?? "No dominant risk driver recorded."}
                </p>
                <p className="text-[11px] text-slate-500">
                  {risk.open_findings} open findings · model {risk.model_version}
                </p>
              </div>
            </div>
            <div className="mt-5 space-y-3">
              {risk.factors.length === 0 ? (
                <p className="text-xs text-slate-500">No contributing risk factors for this company.</p>
              ) : (
                risk.factors.map((factor) => (
                  <div key={factor.key}>
                    <div className="flex items-center justify-between gap-2 text-xs">
                      <span className="truncate text-slate-300" title={factor.description ?? factor.label}>
                        {factor.label}
                      </span>
                      <span className="num shrink-0 text-slate-400">
                        +{factor.contribution.toFixed(2)}
                      </span>
                    </div>
                    <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-raised">
                      <div
                        className="h-full rounded-full bg-brand-500"
                        style={{ width: `${Math.min(100, Math.round(factor.weight * 100))}%` }}
                      />
                    </div>
                  </div>
                ))
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Asset mix</CardTitle>
            <p className="mt-1 text-xs text-slate-500">{formatNumber(metrics.total_assets)} tracked assets by type.</p>
          </CardHeader>
          <CardContent>
            {assetMix.length === 0 ? (
              <EmptyState icon={Globe2} title="No assets yet" description="Register assets or run authorized discovery." className="py-8" />
            ) : (
              <div className="flex flex-col items-center gap-4 sm:flex-row lg:flex-col xl:flex-row">
                <div className="h-40 w-40 shrink-0">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie data={assetMix} dataKey="count" nameKey="label" innerRadius={44} outerRadius={66} paddingAngle={2} stroke="none">
                        {assetMix.map((entry, index) => (
                          <Cell key={entry.asset_type} fill={CHART_PALETTE[index % CHART_PALETTE.length]} />
                        ))}
                      </Pie>
                      <ChartTooltip contentStyle={TOOLTIP_STYLE} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                <ul className="w-full space-y-1.5">
                  {assetMix.map((entry, index) => (
                    <li key={entry.asset_type} className="flex items-center gap-2 text-xs">
                      <span
                        aria-hidden="true"
                        className="h-2 w-2 shrink-0 rounded-sm"
                        style={{ backgroundColor: CHART_PALETTE[index % CHART_PALETTE.length] }}
                      />
                      <span className="min-w-0 flex-1 truncate text-slate-400">{entry.label}</span>
                      <span className="num text-slate-300">{entry.count}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Service exposure</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            {[
              ["Observed services", data.service_snapshot.total],
              ["Flagged risky", data.service_snapshot.risky],
              ["Unexpected services", data.service_snapshot.unexpected],
              ["Unencrypted protocols", data.service_snapshot.unencrypted],
              ["Management interfaces", data.service_snapshot.management_interfaces],
            ].map(([label, value]) => (
              <div key={String(label)} className="flex items-center justify-between gap-3 border-b border-border/60 pb-2 last:border-0 last:pb-0">
                <span className="text-xs text-slate-400">{label}</span>
                <span className="num text-sm font-medium text-slate-200">{formatNumber(Number(value))}</span>
              </div>
            ))}
            <Link to="/ips" className="inline-flex items-center gap-1 pt-1 text-xs font-medium text-brand-400 hover:text-brand-300">
              Open services inventory <ArrowRight aria-hidden="true" className="h-3 w-3" />
            </Link>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Certificate health</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            {[
              ["Certificates tracked", data.certificate_snapshot.total],
              ["Valid", data.certificate_snapshot.valid],
              ["Expiring soon", data.certificate_snapshot.expiring_soon],
              ["Expired", data.certificate_snapshot.expired],
              ["Hostname mismatch", data.certificate_snapshot.hostname_mismatch],
            ].map(([label, value]) => (
              <div key={String(label)} className="flex items-center justify-between gap-3 border-b border-border/60 pb-2 last:border-0 last:pb-0">
                <span className="text-xs text-slate-400">{label}</span>
                <span className="num text-sm font-medium text-slate-200">{formatNumber(Number(value))}</span>
              </div>
            ))}
            <p className="text-[11px] text-slate-500">
              {data.certificate_snapshot.closest_expiry_days === null
                ? "No upcoming expiry recorded."
                : `Closest expiry in ${data.certificate_snapshot.closest_expiry_days} day(s).`}
            </p>
            <Link to="/certificates" className="inline-flex items-center gap-1 text-xs font-medium text-brand-400 hover:text-brand-300">
              Review certificates <ArrowRight aria-hidden="true" className="h-3 w-3" />
            </Link>
          </CardContent>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Findings by severity</CardTitle>
          </CardHeader>
          <CardContent>
            {findingsTotal === 0 ? (
              <EmptyState icon={ShieldCheck} title="No open findings" description="Nothing currently needs remediation." className="py-8" />
            ) : (
              <SeverityBars title="Findings" counts={data.findings_by_severity} total={findingsTotal} href="/findings" />
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Vulnerabilities by severity</CardTitle>
          </CardHeader>
          <CardContent>
            {vulnerabilitiesTotal === 0 ? (
              <EmptyState icon={ShieldCheck} title="No tracked vulnerabilities" description="No CVE records are open for this company." className="py-8" />
            ) : (
              <SeverityBars
                title="Vulnerabilities"
                counts={data.vulnerabilities_by_severity}
                total={vulnerabilitiesTotal}
                href="/vulnerabilities"
              />
            )}
          </CardContent>
        </Card>
      </div>

      <Card className="mt-4">
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>Top risks</CardTitle>
            <p className="mt-1 text-xs text-slate-500">Highest scored open findings, adjusted for exposure and business impact.</p>
          </div>
          <Link to="/findings" className="text-xs font-medium text-brand-400 hover:text-brand-300">
            All findings
          </Link>
        </CardHeader>
        <CardContent className="p-0 sm:p-0">
          {data.top_risks.length === 0 ? (
            <EmptyState icon={ShieldCheck} title="No open risks" description="Open findings will be prioritised here." className="py-10" />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-y border-border text-left text-[11px] uppercase tracking-wide text-slate-500">
                    <th className="px-4 py-2.5 font-medium">Risk</th>
                    <th className="px-4 py-2.5 font-medium">Finding</th>
                    <th className="hidden px-4 py-2.5 font-medium md:table-cell">Severity</th>
                    <th className="hidden px-4 py-2.5 font-medium lg:table-cell">Asset</th>
                    <th className="px-4 py-2.5 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {data.top_risks.map((finding) => (
                    <tr key={finding.id} className="transition-colors hover:bg-surface-raised/50">
                      <td className="whitespace-nowrap px-4 py-3">
                        <span className={`num text-sm font-semibold ${riskTextClass(finding.severity, finding.risk_score)}`}>
                          {finding.risk_score.toFixed(1)}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <Link to={`/findings?focus=${finding.id}`} className="line-clamp-1 font-medium text-slate-200 hover:text-brand-400">
                          {finding.title}
                        </Link>
                        <p className="mt-0.5 line-clamp-1 text-xs text-slate-500">
                          {titleize(finding.finding_type)} · {finding.confidence} confidence
                        </p>
                      </td>
                      <td className="hidden px-4 py-3 md:table-cell">
                        <SeverityBadge severity={finding.severity} />
                      </td>
                      <td className="hidden max-w-[16rem] px-4 py-3 lg:table-cell">
                        {finding.asset_id ? (
                          <Link to={`/assets/${finding.asset_id}`} className="line-clamp-1 text-xs text-slate-400 hover:text-brand-400">
                            {finding.asset_name ?? "Asset"}
                          </Link>
                        ) : (
                          <span className="text-xs text-slate-500">Unlinked</span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge status={finding.status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Recent activity</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {data.recent_events.length === 0 ? (
              <EmptyState icon={Activity} title="No recorded events" description="Asset changes and verifications will appear here." className="py-8" />
            ) : (
              <ul className="divide-y divide-border/60">
                {data.recent_events.slice(0, 6).map((event) => (
                  <li key={`${event.kind}-${event.id}`} className="flex gap-3 px-4 py-3">
                    <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-brand-500/70" />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-start justify-between gap-3">
                        <p className="truncate text-sm text-slate-200">{event.title}</p>
                        <span className="shrink-0 text-[11px] text-slate-500">{relativeTime(event.occurred_at)}</span>
                      </div>
                      {event.detail ? <p className="mt-0.5 line-clamp-2 text-xs text-slate-500">{event.detail}</p> : null}
                      {event.asset_id ? (
                        <Link to={`/assets/${event.asset_id}`} className="mt-1 inline-block text-[11px] font-medium text-brand-400 hover:text-brand-300">
                          {event.asset_name ?? "View asset"}
                        </Link>
                      ) : null}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <div className="grid gap-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle>Recent alerts</CardTitle>
              <Link to="/alerts" className="text-xs font-medium text-brand-400 hover:text-brand-300">
                Alert center
              </Link>
            </CardHeader>
            <CardContent className="p-0">
              {data.recent_alerts.length === 0 ? (
                <EmptyState icon={ShieldCheck} title="No recent alerts" description="Notifications are raised for meaningful changes." className="py-6" />
              ) : (
                <ul className="divide-y divide-border/60">
                  {data.recent_alerts.slice(0, 4).map((alert) => (
                    <li key={alert.id} className="flex items-start gap-3 px-4 py-3">
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm text-slate-200">{alert.title}</p>
                        <p className="mt-0.5 text-[11px] text-slate-500">{relativeTime(alert.occurred_at)}</p>
                      </div>
                      {alert.severity ? <SeverityBadge severity={alert.severity} dot={false} /> : null}
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle>Recent changes</CardTitle>
              <Link to="/changes" className="text-xs font-medium text-brand-400 hover:text-brand-300">
                Change history
              </Link>
            </CardHeader>
            <CardContent className="p-0">
              {data.recent_changes.length === 0 ? (
                <EmptyState icon={Activity} title="No configuration changes" description="DNS, service and certificate changes are tracked here." className="py-6" />
              ) : (
                <ul className="divide-y divide-border/60">
                  {data.recent_changes.slice(0, 4).map((change) => (
                    <li key={change.id} className="flex items-start gap-3 px-4 py-3">
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm text-slate-200">{change.title}</p>
                        <p className="mt-0.5 text-[11px] text-slate-500">{relativeTime(change.occurred_at)}</p>
                      </div>
                      {change.severity ? <SeverityBadge severity={change.severity} dot={false} /> : null}
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {comparison.length > 0 ? (
        <Card className="mt-4">
          <CardHeader>
            <CardTitle>Company comparison</CardTitle>
            <p className="mt-1 text-xs text-slate-500">
              Authorized cross-company view shown only to platform administrators. Excludes archived companies.
            </p>
          </CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-y border-border text-left text-[11px] uppercase tracking-wide text-slate-500">
                    <th className="px-4 py-2.5 font-medium">Company</th>
                    <th className="px-4 py-2.5 text-right font-medium">Assets</th>
                    <th className="px-4 py-2.5 text-right font-medium">Open findings</th>
                    <th className="px-4 py-2.5 text-right font-medium">Critical</th>
                    <th className="px-4 py-2.5 text-right font-medium">Risk score</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {[data.companies.find((entry) => entry.company_id === selectedCompanyId), ...comparison]
                    .filter((entry): entry is (typeof data.companies)[number] => Boolean(entry))
                    .map((entry) => (
                      <tr
                        key={entry.company_id}
                        className={`transition-colors hover:bg-surface-raised/50 ${
                          entry.company_id === selectedCompanyId ? "bg-brand-500/5" : ""
                        }`}
                      >
                        <td className="px-4 py-3">
                          <span className="font-medium text-slate-200">{entry.name}</span>
                          {entry.company_id === selectedCompanyId ? (
                            <span className="ml-2 text-[10px] uppercase tracking-wide text-brand-400">Current</span>
                          ) : null}
                        </td>
                        <td className="num px-4 py-3 text-right text-slate-300">{formatNumber(entry.asset_count)}</td>
                        <td className="num px-4 py-3 text-right text-slate-300">{formatNumber(entry.open_findings)}</td>
                        <td className="num px-4 py-3 text-right text-slate-300">{formatNumber(entry.critical_findings)}</td>
                        <td className="px-4 py-3 text-right">
                          <RiskBadge score={entry.risk_score} />
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      ) : null}

      <p className="mt-6 flex items-center gap-1.5 text-[11px] text-slate-500">
        <Info aria-hidden="true" className="h-3.5 w-3.5" />
        Risk scores are explainable model outputs, not a guarantee of security. {risk.note ?? ""}
      </p>
    </div>
  );
}

export default DashboardPage;
