import { useMemo } from "react";
import { NavLink } from "react-router-dom";
import { PanelLeftClose, PanelLeftOpen, ShieldHalf } from "lucide-react";

import { navigationSections } from "@/config/navigation";
import { useAuth } from "@/context/AuthProvider";
import { cn } from "@/lib/utils";

export type SidebarProps = {
  collapsed: boolean;
  onToggleCollapsed: () => void;
  className?: string;
};

export function Sidebar({
  collapsed,
  onToggleCollapsed,
  className,
}: SidebarProps) {
  const { can } = useAuth();
  const sections = useMemo(
    () =>
      navigationSections
        .map((section) => ({
          ...section,
          items: section.items.filter((item) => can(item.permission)),
        }))
        .filter((section) => section.items.length > 0),
    [can],
  );

  return (
    <aside
      aria-label="Primary"
      className={cn(
        "flex h-full shrink-0 flex-col border-r border-border bg-surface transition-[width] duration-200",
        collapsed ? "w-16" : "w-64",
        className,
      )}
    >
      <div
        className={cn(
          "flex h-14 items-center gap-2.5 border-b border-border px-3",
          collapsed && "justify-center px-0",
        )}
      >
        <ShieldHalf aria-hidden="true" className="h-6 w-6 shrink-0 text-brand-500" />
        {collapsed ? null : (
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-slate-100">
              ASM Platform
            </p>
            <p className="truncate text-[11px] text-slate-500">
              External attack surface
            </p>
          </div>
        )}
      </div>

      <nav className="flex-1 overflow-y-auto px-2 py-3">
        {sections.map((section) => (
          <div key={section.title} className="mb-3 last:mb-0">
            {collapsed ? (
              <span
                aria-hidden="true"
                className="mx-2 mb-2 block border-t border-border"
              />
            ) : (
              <p className="px-3 pb-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                {section.title}
              </p>
            )}
            <ul className="flex flex-col gap-0.5">
              {section.items.map((item) => (
                <li key={item.path}>
                  <NavLink
                    to={item.path}
                    aria-label={collapsed ? item.label : undefined}
                    title={collapsed ? item.label : undefined}
                    className={({ isActive }) =>
                      cn(
                        "sidebar-link",
                        collapsed && "justify-center px-2",
                        isActive && "sidebar-link-active",
                      )
                    }
                  >
                    <item.icon aria-hidden="true" className="h-4 w-4 shrink-0" />
                    {collapsed ? null : (
                      <span className="truncate">{item.label}</span>
                    )}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>

      <div className="border-t border-border p-2">
        <button
          type="button"
          onClick={onToggleCollapsed}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-expanded={!collapsed}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className={cn(
            "sidebar-link",
            collapsed && "justify-center px-2",
          )}
        >
          {collapsed ? (
            <PanelLeftOpen aria-hidden="true" className="h-4 w-4" />
          ) : (
            <>
              <PanelLeftClose aria-hidden="true" className="h-4 w-4" />
              Collapse
            </>
          )}
        </button>
      </div>
    </aside>
  );
}
