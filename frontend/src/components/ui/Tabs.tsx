import { useRef, type KeyboardEvent, type ReactNode } from "react";

import { cn } from "@/lib/utils";

export type TabItem = {
  value: string;
  label: ReactNode;
  icon?: ReactNode;
  content: ReactNode;
  disabled?: boolean;
};

export type TabsProps = {
  value: string;
  onValueChange: (value: string) => void;
  items: TabItem[];
  className?: string;
  fill?: boolean;
};

export function Tabs({
  value,
  onValueChange,
  items,
  className,
  fill = false,
}: TabsProps) {
  const tabRefs = useRef<Record<string, HTMLButtonElement | null>>({});
  const enabled = items.filter((item) => !item.disabled);

  const moveFocus = (direction: 1 | -1) => {
    if (enabled.length === 0) return;
    const currentIndex = enabled.findIndex((item) => item.value === value);
    const nextIndex =
      currentIndex === -1
        ? 0
        : (currentIndex + direction + enabled.length) % enabled.length;
    const next = enabled[nextIndex];
    onValueChange(next.value);
    tabRefs.current[next.value]?.focus();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    switch (event.key) {
      case "ArrowRight":
      case "ArrowDown":
        event.preventDefault();
        moveFocus(1);
        break;
      case "ArrowLeft":
      case "ArrowUp":
        event.preventDefault();
        moveFocus(-1);
        break;
      case "Home":
        event.preventDefault();
        onValueChange(enabled[0]?.value ?? value);
        tabRefs.current[enabled[0]?.value ?? ""]?.focus();
        break;
      case "End": {
        event.preventDefault();
        const last = enabled[enabled.length - 1];
        onValueChange(last?.value ?? value);
        tabRefs.current[last?.value ?? ""]?.focus();
        break;
      }
    }
  };

  const activeItem = items.find((item) => item.value === value);

  return (
    <div className={cn("flex flex-col gap-4", className)}>
      <div
        role="tablist"
        aria-orientation="horizontal"
        onKeyDown={onKeyDown}
        className="flex items-center gap-1 border-b border-border"
      >
        {items.map((item) => {
          const selected = item.value === value;
          return (
            <button
              key={item.value}
              ref={(node) => {
                tabRefs.current[item.value] = node;
              }}
              type="button"
              role="tab"
              id={`tab-${item.value}`}
              aria-selected={selected}
              aria-controls={`panel-${item.value}`}
              tabIndex={selected ? 0 : -1}
              disabled={item.disabled}
              onClick={() => onValueChange(item.value)}
              className={cn(
                "-mb-px inline-flex items-center gap-2 border-b-2 px-3 py-2 text-sm transition-colors",
                fill && "flex-1 justify-center",
                selected
                  ? "border-brand-500 text-brand-400"
                  : "border-transparent text-slate-400 hover:text-slate-100",
                item.disabled && "cursor-not-allowed opacity-50 hover:text-slate-400",
              )}
            >
              {item.icon ? (
                <span aria-hidden="true" className="inline-flex">
                  {item.icon}
                </span>
              ) : null}
              {item.label}
            </button>
          );
        })}
      </div>

      {activeItem ? (
        <div
          role="tabpanel"
          id={`panel-${activeItem.value}`}
          aria-labelledby={`tab-${activeItem.value}`}
          tabIndex={0}
          className="outline-none"
        >
          {activeItem.content}
        </div>
      ) : null}
    </div>
  );
}
