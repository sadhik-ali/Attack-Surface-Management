import {
  cloneElement,
  isValidElement,
  useEffect,
  useId,
  useRef,
  useState,
  type ReactElement,
  type ReactNode,
} from "react";

import { cn } from "@/lib/utils";

const SIDE_CLASSES = {
  top: "bottom-full left-1/2 mb-2 -translate-x-1/2",
  bottom: "top-full left-1/2 mt-2 -translate-x-1/2",
  right: "left-full top-1/2 ml-2 -translate-y-1/2",
  left: "right-full top-1/2 mr-2 -translate-y-1/2",
} as const;

export type TooltipProps = {
  content: ReactNode;
  children: ReactNode;
  side?: keyof typeof SIDE_CLASSES;
  delay?: number;
  className?: string;
};

export function Tooltip({
  content,
  children,
  side = "top",
  delay = 200,
  className,
}: TooltipProps) {
  const [open, setOpen] = useState(false);
  const timerRef = useRef<number | null>(null);
  const tooltipId = useId();

  const clearTimer = () => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  };

  useEffect(() => clearTimer, []);

  const show = () => {
    clearTimer();
    timerRef.current = window.setTimeout(() => setOpen(true), delay);
  };

  const hide = () => {
    clearTimer();
    setOpen(false);
  };

  const trigger =
    isValidElement(children) &&
    typeof children.type !== "string" &&
    typeof children.type !== "function"
      ? cloneElement(children as ReactElement<Record<string, unknown>>, {
          "aria-describedby": open ? tooltipId : undefined,
        })
      : children;

  return (
    <span
      className={cn("relative inline-flex", className)}
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={hide}
      onKeyDown={(event) => {
        if (event.key === "Escape") hide();
      }}
    >
      {trigger}
      {open ? (
        <span
          role="tooltip"
          id={tooltipId}
          className={cn(
            "pointer-events-none absolute z-50 max-w-xs whitespace-nowrap rounded-md border border-border bg-surface-raised px-2 py-1 text-xs text-slate-200 shadow-overlay",
            SIDE_CLASSES[side],
          )}
        >
          {content}
        </span>
      ) : null}
    </span>
  );
}
