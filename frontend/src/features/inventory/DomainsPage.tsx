import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Globe2, Network, ShieldCheck, RotateCcw } from "lucide-react";

import { PageHeader } from "@/components/common/PageHeader";
import { HttpStatusBadge, RiskBadge } from "@/components/common/Badges";
import { SearchInput, TableLoading } from "@/components/common/TableState";
import {
  Badge,
  Button,
  Card,
  CardContent,
  EmptyState,
  ErrorState,
  Pagination,
  Select,
  Table,
  TBody,
  Td,
  Th,
  THead,
  Tr,
} from "@/components/ui";
import { apiRequest, errorMessage } from "@/lib/api";
import type { DomainRow, Page } from "@/lib/apiTypes";
import { relativeTime } from "@/lib/utils";
import { useAuth } from "@/context/AuthProvider";

export function DomainsPage() {
  const { selectedCompanyId } = useAuth();
  const [search, setSearch] = useState("");
  const [kind, setKind] = useState("");
  const [certificate, setCertificate] = useState("");
  const [page, setPage] = useState(1);
  const pageSize = 25;
  const [sort, setSort] = useState("risk_score");
  const [order, setOrder] = useState<"asc" | "desc">("desc");

  const query = useQuery({
    queryKey: ["domains", selectedCompanyId, search, kind, certificate, page, pageSize, sort, order],
    queryFn: () =>
      apiRequest<Page<DomainRow>>(`/companies/${selectedCompanyId}/domains`, {
        params: {
          q: search.trim() || undefined,
          is_subdomain: kind === "" ? undefined : kind === "subdomain",
          has_certificate: certificate === "" ? undefined : certificate === "true",
          page,
          page_size: pageSize,
          sort,
          order,
        },
      }),
    enabled: Boolean(selectedCompanyId),
    placeholderData: (previous) => previous,
  });

  const reset = () => {
    setSearch("");
    setKind("");
    setCertificate("");
    setPage(1);
  };
  const toggleSort = (key: string) => {
    if (sort === key) setOrder((current) => (current === "desc" ? "asc" : "desc"));
    else {
      setSort(key);
      setOrder(key === "fqdn" ? "asc" : "desc");
    }
    setPage(1);
  };

  const data = query.data;
  const items = data?.items ?? [];

  if (!selectedCompanyId) return null;

  return (
    <div>
      <PageHeader
        title="Domains & subdomains"
        description="Root domains and hostnames in the authorized inventory. Resolved addresses and HTTP observations are only recorded when a permitted scan observes them."
        actions={
          <Link to="/assets?asset_type=domain">
            <Button variant="ghost" size="sm">
              <Globe2 aria-hidden="true" className="h-4 w-4" />
              Asset inventory
            </Button>
          </Link>
        }
      />

      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <div className="metric-card">
          <div className="flex items-center gap-2 text-xs text-slate-500"><Globe2 className="h-3.5 w-3.5" /> Domains matching</div>
          <p className="mt-1 text-2xl font-semibold text-slate-50">{data ? data.total : "—"}</p>
        </div>
        <div className="metric-card">
          <div className="flex items-center gap-2 text-xs text-slate-500"><Network className="h-3.5 w-3.5" /> Resolved hostnames on page</div>
          <p className="mt-1 text-2xl font-semibold text-slate-50">{items.filter((item) => item.resolves_to.length > 0).length}</p>
        </div>
        <div className="metric-card">
          <div className="flex items-center gap-2 text-xs text-slate-500"><ShieldCheck className="h-3.5 w-3.5" /> Subdomains on page</div>
          <p className="mt-1 text-2xl font-semibold text-slate-50">{items.filter((item) => item.is_subdomain).length}</p>
          <p className="mt-0.5 text-[11px] text-slate-500">Certificate linkage is shown per asset</p>
        </div>
      </div>

      <Card>
        <CardContent className="space-y-3">
          <div className="flex flex-col gap-2 lg:flex-row lg:flex-wrap lg:items-center">
            <SearchInput value={search} onChange={(value) => { setSearch(value); setPage(1); }} placeholder="Search FQDN" />
            <Select aria-label="Domain kind" value={kind} onChange={(event) => { setKind(event.target.value); setPage(1); }} className="lg:w-44">
              <option value="">Apex and subdomains</option>
              <option value="domain">Apex domains</option>
              <option value="subdomain">Subdomains</option>
            </Select>
            <Select aria-label="Certificate filter" value={certificate} onChange={(event) => { setCertificate(event.target.value); setPage(1); }} className="lg:w-48">
              <option value="">Certificate: any</option>
              <option value="true">With certificate</option>
              <option value="false">Without certificate</option>
            </Select>
            {search || kind || certificate ? (
              <Button variant="ghost" size="sm" onClick={reset}>
                <RotateCcw aria-hidden="true" className="h-3.5 w-3.5" /> Reset
              </Button>
            ) : null}
          </div>

          {query.isLoading ? (
            <TableLoading columns={7} />
          ) : query.isError ? (
            <ErrorState title="Could not load domains" message={errorMessage(query.error)} onRetry={() => void query.refetch()} />
          ) : items.length === 0 ? (
            <EmptyState
              icon={Globe2}
              title="No domains found"
              description="Add a root domain, import a CSV, or run an authorized passive discovery scan."
              action={search || kind || certificate ? <Button variant="ghost" size="sm" onClick={reset}>Clear filters</Button> : null}
            />
          ) : (
            <>
              <div className="overflow-x-auto rounded-md border border-border">
                <Table>
                  <THead>
                    <Tr>
                      <Th sortable sortDirection={sort === "fqdn" ? order : undefined} onSort={() => toggleSort("fqdn")}>Domain</Th>
                      <Th className="hidden lg:table-cell">Root</Th>
                      <Th>Kind</Th>
                      <Th className="hidden xl:table-cell">Resolves to</Th>
                      <Th>HTTP</Th>
                      <Th className="hidden lg:table-cell">Technologies</Th>
                      <Th sortable align="right" sortDirection={sort === "risk_score" ? order : undefined} onSort={() => toggleSort("risk_score")}>Risk</Th>
                      <Th sortable className="hidden md:table-cell" sortDirection={sort === "last_seen" ? order : undefined} onSort={() => toggleSort("last_seen")}>Last seen</Th>
                    </Tr>
                  </THead>
                  <TBody>
                    {items.map((domain) => (
                      <Tr key={domain.id}>
                        <Td>
                          <Link to={`/assets/${domain.asset_id}`} className="block max-w-[22rem] truncate font-medium text-slate-200 hover:text-brand-400" title={domain.fqdn}>
                            {domain.fqdn}
                          </Link>
                          <p className="mt-0.5 truncate text-[11px] text-slate-500">{domain.asset_name ?? "Unlinked asset"}</p>
                        </Td>
                        <Td className="hidden lg:table-cell"><span className="text-xs text-slate-400">{domain.root_domain}</span></Td>
                        <Td>
                          <Badge tone={domain.is_subdomain ? "brand" : "neutral"}>{domain.is_subdomain ? "Subdomain" : "Apex"}</Badge>
                          {domain.is_wildcard ? <Badge tone="medium" className="ml-1">Wildcard</Badge> : null}
                        </Td>
                        <Td className="hidden xl:table-cell">
                          <span className="num max-w-[16rem] truncate text-xs text-slate-300" title={domain.resolves_to.join(", ")}>
                            {domain.resolves_to.length > 0 ? domain.resolves_to.join(", ") : "Not resolved"}
                          </span>
                        </Td>
                        <Td><HttpStatusBadge status={domain.http_status} /></Td>
                        <Td className="hidden lg:table-cell">
                          {domain.technologies.length > 0 ? (
                            <span className="line-clamp-1 text-xs text-slate-400" title={domain.technologies.join(", ")}>{domain.technologies.join(", ")}</span>
                          ) : (
                            <span className="text-xs text-slate-500">—</span>
                          )}
                        </Td>
                        <Td align="right"><RiskBadge score={domain.risk_score} /></Td>
                        <Td className="hidden md:table-cell"><span className="text-xs text-slate-500">{domain.last_seen ? relativeTime(domain.last_seen) : "—"}</span></Td>
                      </Tr>
                    ))}
                  </TBody>
                </Table>
              </div>
              <Pagination page={data?.page ?? page} total={data?.total} pageSize={data?.page_size ?? pageSize} onPageChange={setPage} />
            </>
          )}
        </CardContent>
      </Card>
      <p className="mt-4 text-[11px] text-slate-500">
        Domain records are observations, not ownership proof. Scanning always requires a separately approved authorization.
      </p>
    </div>
  );
}

export default DomainsPage;
