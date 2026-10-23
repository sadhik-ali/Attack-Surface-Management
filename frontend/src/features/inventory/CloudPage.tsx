import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Cloud, Info, Lock, RotateCcw, ShieldAlert, Globe2 } from "lucide-react";

import { PageHeader } from "@/components/common/PageHeader";
import { RiskBadge, SourceBadge } from "@/components/common/Badges";
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
import type { CloudResourceRow, CloudSummary, Page } from "@/lib/apiTypes";
import { titleize } from "@/lib/labels";
import { useAuth } from "@/context/AuthProvider";

export function CloudPage() {
  const { selectedCompanyId } = useAuth();
  const [search, setSearch] = useState("");
  const [provider, setProvider] = useState("");
  const [publicAccess, setPublicAccess] = useState("");
  const [encrypted, setEncrypted] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize] = useState(25);
  const [sort, setSort] = useState("risk_score");
  const [order, setOrder] = useState<"asc" | "desc">("desc");

  const summaryQuery = useQuery({
    queryKey: ["cloud-summary", selectedCompanyId],
    queryFn: () => apiRequest<CloudSummary>(`/companies/${selectedCompanyId}/cloud-resources/summary`),
    enabled: Boolean(selectedCompanyId),
  });

  const query = useQuery({
    queryKey: ["cloud-resources", selectedCompanyId, search, provider, publicAccess, encrypted, page, pageSize, sort, order],
    queryFn: () =>
      apiRequest<Page<CloudResourceRow>>(`/companies/${selectedCompanyId}/cloud-resources`, {
        params: {
          q: search.trim() || undefined,
          provider: provider || undefined,
          public_access: publicAccess === "" ? undefined : publicAccess === "true",
          encrypted: encrypted === "" ? undefined : encrypted === "true",
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
  const summary = summaryQuery.data;
  const items = data?.items ?? [];
  const liveRows = items.filter((item) => item.source !== "seed").length;
  const sampleRows = items.length - liveRows;
  const reset = () => {
    setSearch("");
    setProvider("");
    setPublicAccess("");
    setEncrypted("");
    setPage(1);
  };

  if (!selectedCompanyId) return null;

  return (
    <div>
      <PageHeader
        title="Cloud resources"
        description="Cloud accounts and resources reported to the platform. No live cloud provider connector is implemented in this build; rows carry their source so sample fixtures are never presented as live inventory."
      />

      <div className="mb-4 flex items-start gap-2.5 rounded-lg border border-medium/25 bg-medium/5 px-3.5 py-2.5 text-xs text-slate-400">
        <Info aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-medium" />
        <p className="leading-relaxed">
          <span className="font-medium text-slate-200">Integration status: not implemented.</span> AWS, Azure and GCP
          configuration collection requires credentials and is deliberately absent. Sample rows are demonstration
          fixtures and are labelled <span className="font-medium text-medium">Sample data</span>; they must not be used
          as evidence of a real cloud posture.
        </p>
      </div>

      <div className="mb-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <div className="metric-card">
          <div className="flex items-center gap-2 text-xs text-slate-500"><Cloud className="h-3.5 w-3.5" /> Resources</div>
          <p className="mt-1 text-2xl font-semibold text-slate-50">{summary?.total ?? "—"}</p>
        </div>
        <div className="metric-card">
          <div className="flex items-center gap-2 text-xs text-slate-500"><Globe2 className="h-3.5 w-3.5" /> Public access</div>
          <p className="mt-1 text-2xl font-semibold text-critical">{summary?.public ?? "—"}</p>
        </div>
        <div className="metric-card">
          <div className="flex items-center gap-2 text-xs text-slate-500"><Lock className="h-3.5 w-3.5" /> Unencrypted</div>
          <p className="mt-1 text-2xl font-semibold text-high">{summary?.unencrypted ?? "—"}</p>
        </div>
        <div className="metric-card">
          <div className="flex items-center gap-2 text-xs text-slate-500"><ShieldAlert className="h-3.5 w-3.5" /> Logging disabled</div>
          <p className="mt-1 text-2xl font-semibold text-medium">{summary?.no_logging ?? "—"}</p>
        </div>
        <div className="metric-card">
          <p className="text-xs uppercase tracking-wide text-slate-500">Provenance on page</p>
          <p className="mt-1 text-sm text-slate-200">{liveRows} reported · {sampleRows} sample</p>
          <p className="mt-0.5 text-[11px] text-slate-500">Based on visible rows</p>
        </div>
      </div>

      <Card>
        <CardContent className="space-y-3">
          <div className="flex flex-col gap-2 lg:flex-row lg:flex-wrap lg:items-center">
            <SearchInput value={search} onChange={(value) => { setSearch(value); setPage(1); }} placeholder="Search resource ID" />
            <Select aria-label="Cloud provider" value={provider} onChange={(event) => { setProvider(event.target.value); setPage(1); }} className="lg:w-40">
              <option value="">All providers</option>
              {(summary?.by_provider ?? []).map((entry) => (
                <option key={entry.provider} value={entry.provider}>{titleize(entry.provider)}</option>
              ))}
            </Select>
            <Select aria-label="Public access filter" value={publicAccess} onChange={(event) => { setPublicAccess(event.target.value); setPage(1); }} className="lg:w-44">
              <option value="">Public: any</option>
              <option value="true">Publicly accessible</option>
              <option value="false">Not public</option>
            </Select>
            <Select aria-label="Encryption filter" value={encrypted} onChange={(event) => { setEncrypted(event.target.value); setPage(1); }} className="lg:w-44">
              <option value="">Encryption: any</option>
              <option value="true">Encrypted</option>
              <option value="false">Not encrypted</option>
            </Select>
            {search || provider || publicAccess || encrypted ? (
              <Button variant="ghost" size="sm" onClick={reset}><RotateCcw aria-hidden="true" className="h-3.5 w-3.5" /> Reset</Button>
            ) : null}
          </div>

          {query.isLoading ? (
            <TableLoading columns={7} />
          ) : query.isError ? (
            <ErrorState title="Could not load cloud resources" message={errorMessage(query.error)} onRetry={() => void query.refetch()} />
          ) : items.length === 0 ? (
            <EmptyState
              icon={Cloud}
              title="No cloud resources recorded"
              description="No connector is configured. Manually registered cloud assets can still appear in the asset inventory."
              action={search || provider || publicAccess || encrypted ? <Button variant="ghost" size="sm" onClick={reset}>Clear filters</Button> : null}
            />
          ) : (
            <>
              <div className="overflow-x-auto rounded-md border border-border">
                <Table>
                  <THead>
                    <Tr>
                      <Th>Resource</Th>
                      <Th sortable sortDirection={sort === "provider" ? order : undefined} onSort={() => { if (sort === "provider") setOrder(order === "desc" ? "asc" : "desc"); else { setSort("provider"); setOrder("asc"); } }}>Provider</Th>
                      <Th className="hidden lg:table-cell">Type</Th>
                      <Th className="hidden xl:table-cell">Region</Th>
                      <Th>Exposure</Th>
                      <Th className="hidden md:table-cell">Encryption</Th>
                      <Th>Source</Th>
                      <Th sortable align="right" sortDirection={sort === "risk_score" ? order : undefined} onSort={() => { if (sort === "risk_score") setOrder(order === "desc" ? "asc" : "desc"); else { setSort("risk_score"); setOrder("desc"); } }}>Risk</Th>
                    </Tr>
                  </THead>
                  <TBody>
                    {items.map((resource) => (
                      <Tr key={resource.id}>
                        <Td>
                          <Link to={`/assets/${resource.asset_id}`} className="block max-w-[22rem] truncate font-medium text-slate-200 hover:text-brand-400" title={resource.external_id}>
                            {resource.external_id}
                          </Link>
                          <p className="truncate text-[11px] text-slate-500">
                            {resource.asset_name ?? "Unlinked asset"}{resource.account_alias ? ` · ${resource.account_alias}` : ""}
                          </p>
                        </Td>
                        <Td><Badge tone="brand">{titleize(resource.provider)}</Badge></Td>
                        <Td className="hidden lg:table-cell"><span className="text-xs text-slate-400">{resource.resource_type ? titleize(resource.resource_type) : "—"}</span></Td>
                        <Td className="hidden xl:table-cell"><span className="text-xs text-slate-400">{resource.region ?? "—"}</span></Td>
                        <Td><Badge tone={resource.public_access ? "critical" : "low"}>{resource.public_access ? "Public" : "Restricted"}</Badge></Td>
                        <Td className="hidden md:table-cell"><Badge tone={resource.encrypted ? "low" : "high"}>{resource.encrypted ? "Encrypted" : "Not encrypted"}</Badge></Td>
                        <Td><SourceBadge source={resource.source} /></Td>
                        <Td align="right"><RiskBadge score={resource.risk_score} /></Td>
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
    </div>
  );
}

export default CloudPage;
