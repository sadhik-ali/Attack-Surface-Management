import type { BadgeTone } from "@/components/ui";
import { normalizeSeverity } from "@/lib/utils";

export function titleize(value: string | null | undefined): string {
  if (!value) return "—";
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

export function severityTone(severity: string | null | undefined): BadgeTone {
  const normalized = normalizeSeverity(severity);
  return normalized === "info" ? "info" : normalized;
}

export function severityLabel(severity: string | null | undefined): string {
  const normalized = normalizeSeverity(severity);
  return normalized === "info" ? "Informational" : titleize(normalized);
}

export function riskTone(
  classification: string | null | undefined,
  score?: number,
): BadgeTone {
  const key = (classification ?? "").toLowerCase();
  if (key.includes("critical")) return "critical";
  if (key.includes("high")) return "high";
  if (key.includes("medium") || key.includes("moderate")) return "medium";
  if (key.includes("low")) return "low";
  if (key.includes("info")) return "info";
  if (score !== undefined) {
    if (score >= 8.5) return "critical";
    if (score >= 6.5) return "high";
    if (score >= 4) return "medium";
    if (score > 0) return "low";
  }
  return "info";
}

export function riskTextClass(
  classification: string | null | undefined,
  score?: number,
): string {
  const tone = riskTone(classification, score);
  if (tone === "critical") return "text-critical";
  if (tone === "high") return "text-high";
  if (tone === "medium") return "text-medium";
  if (tone === "low") return "text-low";
  return "text-info";
}

export function statusTone(status: string | null | undefined): BadgeTone {
  const key = (status ?? "").toLowerCase();
  if (
    ["active", "valid", "resolved", "remediated", "verified", "approved", "success", "closed", "completed"].includes(
      key,
    )
  ) {
    return "low";
  }
  if (["new", "open", "queued", "running", "pending", "in_progress", "triaged"].includes(key)) {
    return "brand";
  }
  if (["expired", "failed", "critical", "rejected", "disabled", "blocked"].includes(key)) {
    return "critical";
  }
  if (["expiring_soon", "warning", "suspicious", "high"].includes(key)) {
    return "high";
  }
  if (["acknowledged", "medium"].includes(key)) {
    return "medium";
  }
  if (["dismissed", "archived", "retired", "inactive"].includes(key)) {
    return "neutral";
  }
  return "info";
}

export function provenanceLabel(source: string | null | undefined): {
  label: string;
  tone: BadgeTone;
  description: string;
} {
  switch ((source ?? "").toLowerCase()) {
    case "seed":
      return {
        label: "Sample data",
        tone: "medium",
        description: "Demonstration fixture — not a live observation",
      };
    case "dns":
    case "certificate_transparency":
    case "tls_probe":
    case "http_probe":
    case "port_scan":
    case "active_scan":
    case "passive_dns":
    case "scan":
      return {
        label: "Observed live",
        tone: "low",
        description: "Recorded by an authorized discovery run",
      };
    case "csv_import":
      return {
        label: "Imported CSV",
        tone: "info",
        description: "Imported by a user from a CSV file",
      };
    case "manual":
      return {
        label: "Manually registered",
        tone: "neutral",
        description: "Entered by a user",
      };
    default:
      return {
        label: titleize(source),
        tone: "neutral",
        description: "Stored record",
      };
  }
}

export function findingStatusLabel(status: string): string {
  return titleize(status);
}

export function assetTypeLabel(type: string): string {
  switch (type) {
    case "domain":
      return "Domain";
    case "subdomain":
      return "Subdomain";
    case "ip_address":
      return "IP address";
    case "web_application":
      return "Web application";
    case "api_endpoint":
      return "API endpoint";
    case "cloud_resource":
      return "Cloud resource";
    case "network_service":
      return "Network service";
    default:
      return titleize(type);
  }
}

export function daysLabel(days: number | null | undefined): string {
  if (days === null || days === undefined) return "—";
  if (days < 0) return `${Math.abs(days)}d overdue`;
  if (days === 0) return "today";
  return `${days}d`;
}

export function cvssTone(score: number | null | undefined): BadgeTone {
  if (score === null || score === undefined) return "neutral";
  if (score >= 9) return "critical";
  if (score >= 7) return "high";
  if (score >= 4) return "medium";
  if (score > 0) return "low";
  return "neutral";
}

export function httpStatusTone(status: number | null | undefined): BadgeTone {
  if (status === null || status === undefined) return "neutral";
  if (status >= 500) return "critical";
  if (status >= 400) return "high";
  if (status >= 300) return "medium";
  if (status >= 200) return "low";
  return "neutral";
}

export function percentage(part: number, total: number): number {
  if (!total) return 0;
  return Math.round((part / total) * 100);
}

export const SEVERITY_CHART_COLORS: Record<string, string> = {
  critical: "#EF4444",
  high: "#F97316",
  medium: "#EAB308",
  low: "#3B82F6",
  informational: "#64748B",
};
