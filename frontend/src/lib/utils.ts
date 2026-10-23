import { format, formatDistanceToNowStrict } from "date-fns";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export type Severity = "critical" | "high" | "medium" | "low" | "info";

export type DateInput = string | number | Date | null | undefined;

const FALLBACK = "--";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

function toDate(value: DateInput): Date | null {
  if (value === null || value === undefined || value === "") return null;
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatDate(value: DateInput, fallback = FALLBACK): string {
  const date = toDate(value);
  return date ? format(date, "dd MMM yyyy") : fallback;
}

export function formatDateTime(
  value: DateInput,
  fallback = FALLBACK,
): string {
  const date = toDate(value);
  return date ? format(date, "dd MMM yyyy HH:mm") : fallback;
}

export function relativeTime(value: DateInput, fallback = FALLBACK): string {
  const date = toDate(value);
  if (!date) return fallback;
  const diffMs = Date.now() - date.getTime();
  if (Math.abs(diffMs) < 60_000) return "just now";
  const suffix = diffMs >= 0 ? "ago" : "from now";
  return `${formatDistanceToNowStrict(date)} ${suffix}`;
}

export function formatNumber(
  value: number | null | undefined,
  options?: Intl.NumberFormatOptions,
): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return FALLBACK;
  }
  return new Intl.NumberFormat("en-US", options).format(value);
}

const SEVERITIES: readonly Severity[] = [
  "critical",
  "high",
  "medium",
  "low",
  "info",
];

export function normalizeSeverity(value: unknown): Severity {
  const candidate =
    typeof value === "string" ? value.toLowerCase().trim() : "";
  return (SEVERITIES as readonly string[]).includes(candidate)
    ? (candidate as Severity)
    : "info";
}

const SEVERITY_TEXT: Record<Severity, string> = {
  critical: "text-critical",
  high: "text-high",
  medium: "text-medium",
  low: "text-low",
  info: "text-info",
};

const SEVERITY_BG: Record<Severity, string> = {
  critical: "bg-critical/10 text-critical border-critical/30",
  high: "bg-high/10 text-high border-high/30",
  medium: "bg-medium/10 text-medium border-medium/30",
  low: "bg-low/10 text-low border-low/30",
  info: "bg-info/10 text-info border-info/30",
};

const SEVERITY_DOT: Record<Severity, string> = {
  critical: "bg-critical",
  high: "bg-high",
  medium: "bg-medium",
  low: "bg-low",
  info: "bg-info",
};

export function severityTextClass(severity: Severity | string): string {
  return SEVERITY_TEXT[normalizeSeverity(severity)];
}

export function severityBgClass(severity: Severity | string): string {
  return SEVERITY_BG[normalizeSeverity(severity)];
}

export function severityDotClass(severity: Severity | string): string {
  return SEVERITY_DOT[normalizeSeverity(severity)];
}

export function downloadBlob(
  filename: string,
  mime: string,
  data: BlobPart,
): void {
  const url = URL.createObjectURL(new Blob([data], { type: mime }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
