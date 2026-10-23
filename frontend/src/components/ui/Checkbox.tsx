import {
  forwardRef,
  useEffect,
  useId,
  type InputHTMLAttributes,
  type ReactNode,
} from "react";

import { cn } from "@/lib/utils";

export type CheckboxProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & {
  label?: ReactNode;
  description?: ReactNode;
  error?: ReactNode;
  indeterminate?: boolean;
};

export const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(
  function Checkbox(
    {
      className,
      label,
      description,
      error,
      indeterminate = false,
      id,
      ...props
    },
    ref,
  ) {
    const generatedId = useId();
    const inputId = id ?? generatedId;
    const describedBy =
      [description ? `${inputId}-description` : null, error ? `${inputId}-error` : null]
        .filter(Boolean)
        .join(" ") || undefined;

    const attachRef = (node: HTMLInputElement | null) => {
      if (node) node.indeterminate = indeterminate;
      if (typeof ref === "function") ref(node);
      else if (ref) ref.current = node;
    };

    useEffect(() => {
      if (ref && "current" in ref && ref.current) {
        ref.current.indeterminate = indeterminate;
      }
    }, [indeterminate, ref]);

    return (
      <div className={cn("flex items-start gap-2.5", className)}>
        <input
          ref={attachRef}
          id={inputId}
          type="checkbox"
          aria-describedby={describedBy}
          aria-invalid={error ? true : undefined}
          className={cn(
            "mt-0.5 h-4 w-4 shrink-0 cursor-pointer rounded border-border bg-bg accent-brand-500",
            error && "outline outline-1 outline-critical",
          )}
          {...props}
        />
        {label || description ? (
          <div className="flex flex-col">
            {label ? (
              <label
                htmlFor={inputId}
                className="cursor-pointer text-sm text-slate-200"
              >
                {label}
              </label>
            ) : null}
            {description ? (
              <span
                id={`${inputId}-description`}
                className="text-xs text-slate-500"
              >
                {description}
              </span>
            ) : null}
          </div>
        ) : null}
        {error ? (
          <p id={`${inputId}-error`} className="text-xs text-critical">
            {error}
          </p>
        ) : null}
      </div>
    );
  },
);
