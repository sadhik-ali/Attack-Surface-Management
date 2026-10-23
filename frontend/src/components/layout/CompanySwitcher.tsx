import { useState } from "react";
import { Link } from "react-router-dom";
import { Building2, Check, ChevronDown, Settings2 } from "lucide-react";

import { useClickOutside } from "@/hooks/useClickOutside";
import { useAuth } from "@/context/AuthProvider";
import { cn } from "@/lib/utils";
import { titleize } from "@/lib/labels";
import { riskTone } from "@/lib/labels";
import { Button } from "@/components/ui";

const RISK_DOT: Record<string, string> = {
  critical: "bg-critical",
  high: "bg-high",
  medium: "bg-medium",
  low: "bg-low",
  info: "bg-info",
};

export function CompanySwitcher() {
  const { companies, selectedCompany, selectCompany } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useClickOutside<HTMLDivElement>(() => setOpen(false), open);

  if (companies.length === 0) return null;

  return (
    <div ref={ref} className="relative">
      <Button
        variant="ghost"
        size="sm"
        onClick={() => setOpen((current) => !current)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label="Switch company"
        className="max-w-[15rem]"
      >
        <Building2 aria-hidden="true" className="h-4 w-4 shrink-0 text-brand-400" />
        <span className="hidden truncate sm:inline">
          {selectedCompany?.name ?? "Select company"}
        </span>
        <ChevronDown aria-hidden="true" className="h-3.5 w-3.5 shrink-0" />
      </Button>

      {open ? (
        <div
          role="listbox"
          aria-label="Companies"
          className="absolute right-0 top-full z-50 mt-2 w-80 overflow-hidden rounded-card border border-border bg-surface-raised shadow-overlay"
        >
          <p className="border-b border-border px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Your companies
          </p>
          <ul className="max-h-80 overflow-y-auto py-1">
            {companies.map((company) => {
              const selected = company.company_id === selectedCompany?.company_id;
              return (
                <li key={company.company_id}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={selected}
                    onClick={() => {
                      selectCompany(company.company_id);
                      setOpen(false);
                    }}
                    className={cn(
                      "flex w-full items-start gap-3 px-3 py-2.5 text-left transition-colors hover:bg-surface",
                      selected && "bg-brand-500/5",
                    )}
                  >
                    <span
                      aria-hidden="true"
                      className={cn(
                        "mt-1.5 h-2 w-2 shrink-0 rounded-full",
                        RISK_DOT[riskTone(null, company.risk_score)],
                      )}
                    />
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center justify-between gap-2">
                        <span className="truncate text-sm font-medium text-slate-100">
                          {company.name}
                        </span>
                        {selected ? (
                          <Check
                            aria-hidden="true"
                            className="h-3.5 w-3.5 shrink-0 text-brand-400"
                          />
                        ) : null}
                      </span>
                      <span className="mt-0.5 block truncate text-xs text-slate-500">
                        {titleize(company.role_code)} ·{" "}
                        {company.asset_count.toLocaleString()} assets · risk{" "}
                        {company.risk_score.toFixed(1)}
                      </span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
          <div className="border-t border-border p-1.5">
            <Link
              to="/companies"
              onClick={() => setOpen(false)}
              className="flex items-center gap-2 rounded-md px-2.5 py-2 text-xs text-slate-400 transition-colors hover:bg-surface hover:text-slate-200"
            >
              <Settings2 aria-hidden="true" className="h-3.5 w-3.5" />
              Manage companies
            </Link>
          </div>
        </div>
      ) : null}
    </div>
  );
}
