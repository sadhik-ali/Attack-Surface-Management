import { Link } from "react-router-dom";
import { Building2 } from "lucide-react";

import { EmptyState } from "@/components/ui";

export function NoCompanyState({
  title = "Select a company",
  description = "Choose a company from the switcher in the top bar to see this workspace.",
}: {
  title?: string;
  description?: string;
}) {
  return (
    <EmptyState
      icon={Building2}
      title={title}
      description={description}
      action={
        <Link
          to="/companies"
          className="text-xs font-medium text-brand-400 hover:text-brand-300"
        >
          Manage companies →
        </Link>
      }
    />
  );
}
