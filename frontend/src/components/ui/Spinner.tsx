import { forwardRef, type SVGProps } from "react";

import { cn } from "@/lib/utils";

export type SpinnerProps = SVGProps<SVGSVGElement>;

export const Spinner = forwardRef<SVGSVGElement, SpinnerProps>(
  function Spinner({ className, ...props }, ref) {
    return (
      <svg
        ref={ref}
        role="status"
        aria-label="Loading"
        viewBox="0 0 24 24"
        fill="none"
        className={cn("h-4 w-4 shrink-0 animate-spin", className)}
        {...props}
      >
        <circle
          cx="12"
          cy="12"
          r="9"
          stroke="currentColor"
          strokeOpacity="0.25"
          strokeWidth="3"
        />
        <path
          d="M21 12a9 9 0 0 0-9-9"
          stroke="currentColor"
          strokeWidth="3"
          strokeLinecap="round"
        />
      </svg>
    );
  },
);
