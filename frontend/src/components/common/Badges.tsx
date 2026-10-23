import { Badge } from "@/components/ui";
import {
  cvssTone,
  httpStatusTone,
  provenanceLabel,
  riskTone,
  severityLabel,
  severityTone,
  statusTone,
  titleize,
} from "@/lib/labels";
import type { Provenance } from "@/lib/apiTypes";
import { Tooltip } from "@/components/ui";

export function SeverityBadge({
  severity,
  dot = true,
}: {
  severity: string;
  dot?: boolean;
}) {
  return (
    <Badge tone={severityTone(severity)} dot={dot}>
      {severityLabel(severity)}
    </Badge>
  );
}

export function StatusBadge({ status }: { status: string }) {
  return (
    <Badge tone={statusTone(status)} dot>
      {titleize(status)}
    </Badge>
  );
}

export function RiskBadge({
  score,
  classification,
}: {
  score: number;
  classification?: string | null;
}) {
  return (
    <Badge tone={riskTone(classification, score)}>
      <span className="num">{score.toFixed(1)}</span>
      <span className="opacity-70">
        {classification ? `· ${titleize(classification)}` : ""}
      </span>
    </Badge>
  );
}

export function CvssBadge({ score }: { score: number | null | undefined }) {
  if (score === null || score === undefined) {
    return <span className="text-xs text-slate-500">No CVSS</span>;
  }
  return (
    <Badge tone={cvssTone(score)}>
      <span className="num">{score.toFixed(1)}</span>
    </Badge>
  );
}

export function HttpStatusBadge({ status }: { status: number | null | undefined }) {
  if (status === null || status === undefined) {
    return <span className="text-xs text-slate-500">—</span>;
  }
  return (
    <Badge tone={httpStatusTone(status)}>
      <span className="num">{status}</span>
    </Badge>
  );
}

export function SourceBadge({
  source,
  provenance,
}: {
  source: string;
  provenance?: Provenance | null;
}) {
  const info = provenance
    ? {
        label: provenance.label,
        tone: provenance.is_simulated
          ? ("medium" as const)
          : provenance.is_observed
            ? ("low" as const)
            : ("neutral" as const),
        description: provenance.is_simulated
          ? "Demonstration fixture — not a live observation"
          : provenance.is_observed
            ? "Recorded by an authorized discovery run"
            : "Entered or imported by a user",
      }
    : provenanceLabel(source);
  return (
    <Tooltip content={info.description}>
      <Badge tone={info.tone} dot>
        {info.label}
      </Badge>
    </Tooltip>
  );
}

export function FlagBadge({
  active,
  children,
  tone = "high",
}: {
  active: boolean;
  children: React.ReactNode;
  tone?: "high" | "critical" | "medium" | "brand" | "low";
}) {
  if (!active) return null;
  return <Badge tone={tone}>{children}</Badge>;
}
