import type {
  HTMLAttributes,
  TableHTMLAttributes,
  TdHTMLAttributes,
  ThHTMLAttributes,
} from "react";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";

import { cn } from "@/lib/utils";

export type SortDirection = "asc" | "desc";

export function Table({ className, ...props }: TableHTMLAttributes<HTMLTableElement>) {
  return <table className={cn("w-full border-collapse text-left text-sm", className)} {...props} />;
}

export function THead({ className, ...props }: HTMLAttributes<HTMLTableSectionElement>) {
  return <thead className={cn(className)} {...props} />;
}

export function TBody({ className, ...props }: HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody className={cn(className)} {...props} />;
}

export function TFoot({ className, ...props }: HTMLAttributes<HTMLTableSectionElement>) {
  return (
    <tfoot
      className={cn("border-t border-border bg-surface-raised/40", className)}
      {...props}
    />
  );
}

export function Tr({ className, ...props }: HTMLAttributes<HTMLTableRowElement>) {
  return (
    <tr
      className={cn(
        "border-b border-border last:border-0 hover:bg-surface-raised/60",
        className,
      )}
      {...props}
    />
  );
}

export type ThProps = ThHTMLAttributes<HTMLTableCellElement> & {
  sortable?: boolean;
  sortDirection?: SortDirection;
  onSort?: () => void;
  align?: "left" | "center" | "right";
};

const ALIGN_CLASSES = {
  left: "text-left",
  center: "text-center",
  right: "text-right",
} as const;

export function Th({
  sortable = false,
  sortDirection,
  onSort,
  align = "left",
  className,
  children,
  ...props
}: ThProps) {
  const ariaSort = sortable
    ? sortDirection === "asc"
      ? "ascending"
      : sortDirection === "desc"
        ? "descending"
        : "none"
    : undefined;

  return (
    <th
      scope="col"
      aria-sort={ariaSort}
      className={cn(
        "sticky top-0 z-10 border-b border-border bg-surface-raised px-3 py-2 text-xs font-medium uppercase tracking-wide text-slate-400",
        ALIGN_CLASSES[align],
        className,
      )}
      {...props}
    >
      {sortable ? (
        <button
          type="button"
          onClick={onSort}
          className="inline-flex items-center gap-1.5 rounded text-inherit uppercase tracking-wide transition-colors hover:text-slate-100"
        >
          <span>{children}</span>
          {sortDirection === "asc" ? (
            <ArrowUp aria-hidden="true" className="h-3.5 w-3.5 text-brand-400" />
          ) : sortDirection === "desc" ? (
            <ArrowDown aria-hidden="true" className="h-3.5 w-3.5 text-brand-400" />
          ) : (
            <ArrowUpDown
              aria-hidden="true"
              className="h-3.5 w-3.5 text-slate-500"
            />
          )}
        </button>
      ) : (
        children
      )}
    </th>
  );
}

export type TdProps = TdHTMLAttributes<HTMLTableCellElement> & {
  align?: "left" | "center" | "right";
  numeric?: boolean;
};

export function Td({
  align = "left",
  numeric = false,
  className,
  ...props
}: TdProps) {
  return (
    <td
      className={cn(
        "px-3 py-2 align-middle text-slate-200",
        ALIGN_CLASSES[align],
        numeric && "font-mono tabular-nums",
        className,
      )}
      {...props}
    />
  );
}

export function Caption({ className, ...props }: HTMLAttributes<HTMLTableCaptionElement>) {
  return (
    <caption
      className={cn("border-b border-border px-3 py-2 text-left text-xs text-slate-500", className)}
      {...props}
    />
  );
}
