import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Code2, RotateCcw, ShieldAlert } from "lucide-react";

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
import type { ApiEndpointRow, Page } from "@/lib/apiTypes";
import { titleize } from "@/lib/labels";
import { useAuth } from "@/context/AuthProvider";

const METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"];

export function ApisPage() {
  const { selectedCompanyId } = useAuth();
  const [search, setSearch] = useState("");
  const [method, setMethod] = useState("");
  const [auth, setAuth] = useState("");
  const [unauthenticated, setUnauthenticated] = useState("");
  const [deprecated, setDeprecated] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize] = useState(25);
  const [sort, setSort] = useState("risk_score");
  const [order, setOrder] = useState<"asc" | "desc">("desc");

  const query = useQuery({
    queryKey: ["api-endpoints", selectedCompanyId, search, method, auth, unauthenticated, deprecated, page, pageSize, sort, order],
    queryFn: () =>
      apiRequest<Page<ApiEndpointRow>>(`/companies/${selectedCompanyId}/api-endpoints`, {
        params: {
          q: search.trim() || undefined,
          method: method || undefined,
          requires_auth: auth === "" ? undefined : auth === "true",
          unauthenticated: unauthenticated === "" ? undefined : unauthenticated === "true",
          deprecated: deprecated === "" ? undefined : deprecated === "true",
          page,
          page_size: pageSize,
          sort,
          order,
        },
      }),
    enabled: Boolean(selectedCompanyId),
    placeholderData: (previous) => previous,
  });

  const data = query.data;
  const items = data?.items ?? [];
  const reset = () => {
    setSearch("");
    setMethod("");
    setAuth("");
    setUnauthenticated("");
    setDeprecated("");
    setPage(1);
  };
  const toggleSort = (key: string) => {
    if (sort === key) setOrder((current) => (current === "desc" ? "asc" : "desc"));
    else {
      setSort(key);
      setOrder(key === "url" || key === "method" ? "asc" : "desc");
    }
    setPage(1);
  };
  const flagCount = items.filter((item) => item.unauthenticated_access || item.is_deprecated).length;

  if (!selectedCompanyId) return null;

  return (
    <div>
      <PageHeader
        title="API endpoints"
        description="Documented and discovered HTTP endpoints. Authentication flags reflect what was observed, not a promise that an endpoint is safe."
      />

      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <div className="metric-card">
          <p className="text-xs uppercase tracking-wide text-slate-500">Endpoints matching</p>
          <p className="mt-1 text-2xl font-semibold text-slate-50">{data ? data.total : "—"}</p>
        </div>
        <div className="metric-card">
          <p className="text-xs uppercase tracking-wide text-slate-500">Flagged on this page</p>
          <p className="mt-1 text-2xl font-semibold text-high">{flagCount}</p>
          <p className="mt-0.5 text-[11px] text-slate-500">Unauthenticated or deprecated</p>
        </div>
        <div className="metric-card">
          <p className="text-xs uppercase tracking-wide text-slate-500">Unauthenticated on this page</p>
          <p className="mt-1 text-2xl font-semibold text-critical">{items.filter((item) => item.unauthenticated_access).length}</p>
        </div>
      </div>

      <Card>
        <CardContent className="space-y-3">
          <div className="flex flex-col gap-2 lg:flex-row lg:flex-wrap lg:items-center">
            <SearchInput value={search} onChange={(value) => { setSearch(value); setPage(1); }} placeholder="Search URL or path" />
            <Select aria-label="HTTP method" value={method} onChange={(event) => { setMethod(event.target.value); setPage(1); }} className="lg:w-32">
              <option value="">Any method</option>
              {METHODS.map((item) => <option key={item} value={item}>{item}</option>)}
            </Select>
            <Select aria-label="Authentication requirement" value={auth} onChange={(event) => { setAuth(event.target.value); setPage(1); }} className="lg:w-48">
              <option value="">Auth: any</option>
              <option value="true">Requires authentication</option>
              <option value="false">No auth required</option>
            </Select>
            <Select aria-label="Unauthenticated access" value={unauthenticated} onChange={(event) => { setUnauthenticated(event.target.value); setPage(1); }} className="lg:w-52">
              <option value="">Unauthenticated: any</option>
              <option value="true">Unauthenticated access observed</option>
              <option value="false">No unauthenticated access</option>
            </Select>
            <Select aria-label="Deprecated" value={deprecated} onChange={(event) => { setDeprecated(event.target.value); setPage(1); }} className="lg:w-44">
              <option value="">Deprecated: any</option>
              <option value="true">Deprecated only</option>
              <option value="false">Not deprecated</option>
            </Select>
            {search || method || auth || unauthenticated || deprecated ? (
              <Button variant="ghost" size="sm" onClick={reset}><RotateCcw aria-hidden="true" className="h-3.5 w-3.5" /> Reset</Button>
            ) : null}
          </div>

          {query.isLoading ? (
            <TableLoading columns={7} />
          ) : query.isError ? (
            <ErrorState title="Could not load API endpoints" message={errorMessage(query.error)} onRetry={() => void query.refetch()} />
          ) : items.length === 0 ? (
            <EmptyState
              icon={Code2}
              title="No API endpoints found"
              description="Register an API asset manually, import a CSV, or run authorized discovery capable of observing HTTP endpoints."
              action={search || method || auth || unauthenticated || deprecated ? <Button variant="ghost" size="sm" onClick={reset}>Clear filters</Button> : null}
            />
          ) : (
            <>
              <div className="overflow-x-auto rounded-md border border-border">
                <Table>
                  <THead>
                    <Tr>
                      <Th sortable sortDirection={sort === "url" ? order : undefined} onSort={() => toggleSort("url")}>URL</Th>
                      <Th sortable sortDirection={sort === "method" ? order : undefined} onSort={() => toggleSort("method")}>Method</Th>
                      <Th className="hidden lg:table-cell">Format</Th>
                      <Th className="hidden xl:table-cell">Auth</Th>
                      <Th>Flags</Th>
                      <Th className="hidden md:table-cell">Last status</Th>
                      <Th sortable align="right" sortDirection={sort === "risk_score" ? order : undefined} onSort={() => toggleSort("risk_score")}>Risk</Th>
                    </Tr>
                  </THead>
                  <TBody>
                    {items.map((endpoint) => (
                      <Tr key={endpoint.id}>
                        <Td>
                          <Link to={`/assets/${endpoint.asset_id}`} className="block max-w-[26rem] truncate font-medium text-slate-200 hover:text-brand-400" title={endpoint.url}>
                            {endpoint.url}
                          </Link>
                          <p className="mt-0.5 truncate text-[11px] text-slate-500">{endpoint.asset_name ?? "Unlinked asset"}</p>
                        </Td>
                        <Td><Badge tone="neutral">{endpoint.method}</Badge></Td>
                        <Td className="hidden lg:table-cell"><span className="text-xs text-slate-400">{endpoint.api_format ? titleize(endpoint.api_format) : "—"}</span></Td>
                        <Td className="hidden xl:table-cell">
                          <span className="text-xs text-slate-400">
                            {endpoint.auth_type ? titleize(endpoint.auth_type) : endpoint.requires_auth ? "Required" : "None observed"}
                          </span>
                        </Td>
                        <Td>
                          <div className="flex flex-wrap gap-1">
                            {endpoint.unauthenticated_access ? <Badge tone="critical">Unauthenticated</Badge> : null}
                            {endpoint.is_deprecated ? <Badge tone="high">Deprecated</Badge> : null}
                            {!endpoint.unauthenticated_access && !endpoint.is_deprecated ? <Badge tone="low">No flag</Badge> : null}
                          </div>
                        </Td>
                        <Td className="hidden md:table-cell"><HttpStatusBadge status={endpoint.last_status_code} /></Td>
                        <Td align="right"><RiskBadge score={endpoint.risk_score} /></Td>
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
      <p className="mt-4 flex items-center gap-1.5 text-[11px] text-slate-500">
        <ShieldAlert aria-hidden="true" className="h-3.5 w-3.5" />
        An endpoint without an observed auth challenge is a lead, not a confirmed exposure. Validate before raising it internally.
      </p>
    </div>
  );
}

export default ApisPage;
