import type { CSSProperties } from "react";

export const CHART_PALETTE = [
  "#3B82F6",
  "#22D3EE",
  "#8B5CF6",
  "#F59E0B",
  "#10B981",
  "#EF4444",
  "#64748B",
];

export const CHART_GRID = "#1E2A3C";
export const CHART_AXIS = "#64748B";

export const TOOLTIP_STYLE: CSSProperties = {
  backgroundColor: "#111827",
  border: "1px solid #1E2A3C",
  borderRadius: "8px",
  color: "#E2E8F0",
  fontSize: "12px",
  boxShadow: "0 16px 40px -12px rgb(0 0 0 / 0.6)",
};

export const RISK_COLORS: Record<string, string> = {
  critical: "#EF4444",
  high: "#F97316",
  medium: "#EAB308",
  low: "#3B82F6",
  informational: "#64748B",
  info: "#64748B",
};

export function shortDate(iso: string): string {
  const parts = iso.split("-");
  if (parts.length === 3) return `${parts[1]}/${parts[2]}`;
  return iso;
}
