import { ChevronLeft, ChevronRight } from "lucide-react";

import { cn, formatNumber } from "@/lib/utils";
import { Button } from "./Button";

export type PaginationProps = {
  page: number;
  onPageChange: (page: number) => void;
  pageCount?: number;
  total?: number;
  pageSize?: number;
  className?: string;
  siblingCount?: number;
  showRangeLabel?: boolean;
};

function buildPages(page: number, pageCount: number, siblingCount: number): (number | "gap")[] {
  const slots = siblingCount * 2 + 5;
  if (pageCount <= slots) {
    return Array.from({ length: pageCount }, (_, index) => index + 1);
  }

  const left = Math.max(2, page - siblingCount);
  const right = Math.min(pageCount - 1, page + siblingCount);

  return [
    1,
    ...(left > 2 ? (["gap"] as const) : []),
    ...Array.from({ length: right - left + 1 }, (_, index) => left + index),
    ...(right < pageCount - 1 ? (["gap"] as const) : []),
    pageCount,
  ];
}

export function Pagination({
  page,
  onPageChange,
  pageCount,
  total,
  pageSize,
  className,
  siblingCount = 1,
  showRangeLabel = true,
}: PaginationProps) {
  const resolvedPageCount =
    pageCount ??
    (total !== undefined && pageSize && pageSize > 0
      ? Math.max(1, Math.ceil(total / pageSize))
      : 1);

  const safePage = Math.min(Math.max(1, page), resolvedPageCount);
  const from = total !== undefined && pageSize ? (safePage - 1) * pageSize + 1 : undefined;
  const to =
    total !== undefined && pageSize
      ? Math.min(total, safePage * pageSize)
      : undefined;

  return (
    <nav
      aria-label="Pagination"
      className={cn(
        "flex flex-wrap items-center justify-between gap-3 text-xs text-slate-400",
        className,
      )}
    >
      {showRangeLabel && from !== undefined && to !== undefined ? (
        <p>
          Showing{" "}
          <span className="num text-slate-200">{formatNumber(from)}</span>
          –
          <span className="num text-slate-200">{formatNumber(to)}</span> of{" "}
          <span className="num text-slate-200">{formatNumber(total)}</span>
        </p>
      ) : (
        <span />
      )}

      <div className="flex items-center gap-1">
        <Button
          variant="ghost"
          size="sm"
          aria-label="Previous page"
          disabled={safePage <= 1}
          onClick={() => onPageChange(safePage - 1)}
        >
          <ChevronLeft aria-hidden="true" className="h-4 w-4" />
        </Button>

        {buildPages(safePage, resolvedPageCount, siblingCount).map((entry, index) =>
          entry === "gap" ? (
            <span
              key={`gap-${index}`}
              aria-hidden="true"
              className="px-1 text-slate-500"
            >
              ...
            </span>
          ) : (
            <Button
              key={entry}
              variant={entry === safePage ? "primary" : "ghost"}
              size="sm"
              aria-label={`Page ${entry}`}
              aria-current={entry === safePage ? "page" : undefined}
              onClick={() => onPageChange(entry)}
              className="min-w-8"
            >
              <span className="num">{entry}</span>
            </Button>
          ),
        )}

        <Button
          variant="ghost"
          size="sm"
          aria-label="Next page"
          disabled={safePage >= resolvedPageCount}
          onClick={() => onPageChange(safePage + 1)}
        >
          <ChevronRight aria-hidden="true" className="h-4 w-4" />
        </Button>
      </div>
    </nav>
  );
}
