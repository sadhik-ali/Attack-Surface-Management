import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { Lock, Network, RotateCcw, Server, ShieldAlert, ShieldOff } from "lucide-react";

import { PageHeader } from "@/components/common/PageHeader";
import { RiskBadge } from "@/components/common/Badges";
import { SearchInput, TableLoading } from "@/components/common/TableState";
import {
  Badge,
  Button,
  Card,
  CardContent,
  EmptyState,
  ErrorState,
  Input,
  Pagination,
  Select,
  Table,
  TBody,
  Tabs,
  Td,
  Th,
  THead,
  Tr,
} from "@/components/ui";
import { apiRequest, errorMessage } from "@/lib/api";
import type { IPRow, Page, Service, ServiceSummary } from "@/lib/apiTypes";
import { titleize } from "@/lib/labels";
import { relativeTime } from "@/lib/utils";
import { useAuth } from "@/context/AuthProvider";

function riskTone(level: string | null): "critical" | "high" | "medium" | "low" | "neutral" {
  if (level === "critical") return "critical";
  if (level === "high") return "high";
  if (level === "medium") return "medium";
  if (level === "low") return "low";
  return "neutral";
}

export function IpsPage() {
  const { selectedCompanyId } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = searchParams.get("tab") === "services" ? "services" : "ips";

  const [ipSearch, setIpSearch] = useState("");
  const [version, setVersion] = useState("");
  const [isPrivate, setIsPrivate] = useState("");
  const [provider, setProvider] = useState("");
  const [ipPage, setIpPage] = useState(1);
  const [ipPageSize] = useState(25);
  const [ipSort, setIpSort] = useState("risk_score");
  const [ipOrder, setIpOrder] = useState<"asc" | "desc">("desc");

  const [serviceSearch, setServiceSearch] = useState("");
  const [category, setCategory] = useState("");
  const [risky, setRisky] = useState("");
  const [unexpected, setUnexpected] = useState("");
  const [encrypted, setEncrypted] = useState("");
  const [port, setPort] = useState("");
  const [servicePage, setServicePage] = useState(1);
  const [servicePageSize] = useState(25);

  const ipQuery = useQuery({
    queryKey: ["ips", selectedCompanyId, ipSearch, version, isPrivate, provider, ipPage, ipPageSize, ipSort, ipOrder],
    queryFn: () =>
      apiRequest<Page<IPRow>>(`/companies/${selectedCompanyId}/ip-addresses`, {
        params: {
          q: ipSearch.trim() || undefined,
          version: version || undefined,
          is_private: isPrivate === "" ? undefined : isPrivate === "true",
          provider_hint: provider.trim() || undefined,
          page: ipPage,
          page_size: ipPageSize,
          sort: ipSort,
          order: ipOrder,
        },
      }),
    enabled: Boolean(selectedCompanyId) && tab === "ips",
    placeholderData: (previous) => previous,
  });

  const summaryQuery = useQuery({
    queryKey: ["services-summary", selectedCompanyId],
    queryFn: () => apiRequest<ServiceSummary>(`/companies/${selectedCompanyId}/services/summary`),
    enabled: Boolean(selectedCompanyId) && tab === "services",
  });

  const servicesQuery = useQuery({
    queryKey: ["services", selectedCompanyId, serviceSearch, category, risky, unexpected, encrypted, port, servicePage, servicePageSize],
    queryFn: () =>
      apiRequest<Page<Service>>(`/companies/${selectedCompanyId}/services`, {
        params: {
          q: serviceSearch.trim() || undefined,
          category: category || undefined,
          risky: risky === "" ? undefined : risky === "true",
          unexpected: unexpected === "" ? undefined : unexpected === "true",
          encrypted: encrypted === "" ? undefined : encrypted === "true",
          port: port.trim() ? Number(port) : undefined,
          page: servicePage,
          page_size: servicePageSize,
          sort: "port",
          order: "asc",
        },
      }),
    enabled: Boolean(selectedCompanyId) && tab === "services",
    placeholderData: (previous) => previous,
  });

  const ipData = ipQuery.data;
  const servicesData = servicesQuery.data;
  const summary = summaryQuery.data;
  const ips = ipData?.items ?? [];
  const services = servicesData?.items ?? [];

  const setTab = (value: string) => {
    const next = new URLSearchParams(searchParams);
    if (value === "services") next.set("tab", "services");
    else next.delete("tab");
    setSearchParams(next, { replace: true });
  };

  if (!selectedCompanyId) return null;

  return (
    <div>
      <PageHeader
        title="IPs & services"
        description="Addresses in inventory and the services observed on them. Service rows only appear after an authorized active scan; no ports are probed by viewing this page."
      />

      <Tabs
        value={tab}
        onValueChange={setTab}
        items={[
          { value: "ips", label: "IP addresses", content: null },
          { value: "services", label: "Exposed services", content: null },
        ]}
        className="mb-4"
      />

      {tab === "ips" ? (
        <>
          <div className="mb-4 grid gap-3 sm:grid-cols-3">
            <div className="metric-card">
              <div className="flex items-center gap-2 text-xs text-slate-500"><Network className="h-3.5 w-3.5" /> IP addresses matching</div>
              <p className="mt-1 text-2xl font-semibold text-slate-50">{ipData ? ipData.total : "—"}</p>
            </div>
            <div className="metric-card">
              <div className="flex items-center gap-2 text-xs text-slate-500"><Lock className="h-3.5 w-3.5" /> Private addresses on page</div>
              <p className="mt-1 text-2xl font-semibold text-slate-50">{ips.filter((ip) => ip.is_private).length}</p>
            </div>
            <div className="metric-card">
              <div className="flex items-center gap-2 text-xs text-slate-500"><Server className="h-3.5 w-3.5" /> Services on page</div>
              <p className="mt-1 text-2xl font-semibold text-slate-50">{ips.reduce((sum, ip) => sum + ip.service_count, 0)}</p>
            </div>
          </div>

          <Card>
            <CardContent className="space-y-3">
              <div className="flex flex-col gap-2 lg:flex-row lg:flex-wrap lg:items-center">
                <SearchInput value={ipSearch} onChange={(value) => { setIpSearch(value); setIpPage(1); }} placeholder="Search address or reverse DNS" />
                <Select aria-label="IP version" value={version} onChange={(event) => { setVersion(event.target.value); setIpPage(1); }} className="lg:w-36">
                  <option value="">Any version</option>
                  <option value="ipv4">IPv4</option>
                  <option value="ipv6">IPv6</option>
                </Select>
                <Select aria-label="Private addresses" value={isPrivate} onChange={(event) => { setIsPrivate(event.target.value); setIpPage(1); }} className="lg:w-40">
                  <option value="">Public and private</option>
                  <option value="false">Public only</option>
                  <option value="true">Private only</option>
                </Select>
                <Input
                  aria-label="Provider hint"
                  value={provider}
                  onChange={(event) => { setProvider(event.target.value); setIpPage(1); }}
                  placeholder="Provider (e.g. aws, azure)"
                  className="lg:w-48"
                />
                {ipSearch || version || isPrivate || provider ? (
                  <Button variant="ghost" size="sm" onClick={() => { setIpSearch(""); setVersion(""); setIsPrivate(""); setProvider(""); setIpPage(1); }}>
                    <RotateCcw aria-hidden="true" className="h-3.5 w-3.5" /> Reset
                  </Button>
                ) : null}
              </div>

              {ipQuery.isLoading ? (
                <TableLoading columns={7} />
              ) : ipQuery.isError ? (
                <ErrorState title="Could not load IP addresses" message={errorMessage(ipQuery.error)} onRetry={() => void ipQuery.refetch()} />
              ) : ips.length === 0 ? (
                <EmptyState
                  icon={Network}
                  title="No IP addresses found"
                  description="Directly registered IPs, or addresses observed during authorized DNS and scan activity, appear here."
                />
              ) : (
                <>
                  <div className="overflow-x-auto rounded-md border border-border">
                    <Table>
                      <THead>
                        <Tr>
                          <Th sortable sortDirection={ipSort === "address" ? ipOrder : undefined} onSort={() => { if (ipSort === "address") setIpOrder(ipOrder === "desc" ? "asc" : "desc"); else { setIpSort("address"); setIpOrder("asc"); } }}>Address</Th>
                          <Th className="hidden lg:table-cell">Reverse DNS</Th>
                          <Th>Version</Th>
                          <Th>Scope</Th>
                          <Th className="hidden xl:table-cell">ASN / organisation</Th>
                          <Th className="hidden lg:table-cell">Provider</Th>
                          <Th align="right">Services</Th>
                          <Th sortable align="right" sortDirection={ipSort === "risk_score" ? ipOrder : undefined} onSort={() => { if (ipSort === "risk_score") setIpOrder(ipOrder === "desc" ? "asc" : "desc"); else { setIpSort("risk_score"); setIpOrder("desc"); } }}>Risk</Th>
                          <Th sortable className="hidden md:table-cell" sortDirection={ipSort === "last_seen" ? ipOrder : undefined} onSort={() => { if (ipSort === "last_seen") setIpOrder(ipOrder === "desc" ? "asc" : "desc"); else { setIpSort("last_seen"); setIpOrder("desc"); } }}>Last seen</Th>
                        </Tr>
                      </THead>
                      <TBody>
                        {ips.map((ip) => (
                          <Tr key={ip.id}>
                            <Td>
                              <Link to={`/assets/${ip.asset_id}`} className="num block font-medium text-slate-200 hover:text-brand-400">{ip.address}</Link>
                              <p className="text-[11px] text-slate-500">{ip.asset_name ?? "Unlinked asset"}</p>
                            </Td>
                            <Td className="hidden lg:table-cell"><span className="text-xs text-slate-400">{ip.reverse_dns ?? "—"}</span></Td>
                            <Td><Badge tone="neutral">{ip.version.toUpperCase()}</Badge></Td>
                            <Td><Badge tone={ip.is_private ? "medium" : "brand"}>{ip.is_private ? "Private" : "Public"}</Badge></Td>
                            <Td className="hidden xl:table-cell">
                              <p className="text-xs text-slate-300">{ip.asn ?? "—"}</p>
                              <p className="text-[11px] text-slate-500">{ip.asn_organization ?? "No ASN data"}</p>
                            </Td>
                            <Td className="hidden lg:table-cell"><span className="text-xs text-slate-400">{ip.provider_hint ? titleize(ip.provider_hint) : "—"}</span></Td>
                            <Td align="right"><span className="num text-xs text-slate-300">{ip.service_count}</span></Td>
                            <Td align="right"><RiskBadge score={ip.risk_score} /></Td>
                            <Td className="hidden md:table-cell"><span className="text-xs text-slate-500">{ip.last_seen ? relativeTime(ip.last_seen) : "—"}</span></Td>
                          </Tr>
                        ))}
                      </TBody>
                    </Table>
                  </div>
                  <Pagination page={ipData?.page ?? ipPage} total={ipData?.total} pageSize={ipData?.page_size ?? ipPageSize} onPageChange={setIpPage} />
                </>
              )}
            </CardContent>
          </Card>
        </>
      ) : (
        <>
          <div className="mb-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            <div className="metric-card">
              <p className="text-xs uppercase tracking-wide text-slate-500">Observed services</p>
              <p className="mt-1 text-2xl font-semibold text-slate-50">{summary?.total ?? "—"}</p>
            </div>
            <div className="metric-card">
              <p className="text-xs uppercase tracking-wide text-slate-500">Risky</p>
              <p className="mt-1 text-2xl font-semibold text-critical">{summary?.risky ?? "—"}</p>
            </div>
            <div className="metric-card">
              <p className="text-xs uppercase tracking-wide text-slate-500">Unexpected</p>
              <p className="mt-1 text-2xl font-semibold text-high">{summary?.unexpected ?? "—"}</p>
            </div>
            <div className="metric-card">
              <p className="text-xs uppercase tracking-wide text-slate-500">Unencrypted</p>
              <p className="mt-1 text-2xl font-semibold text-medium">{summary?.unencrypted ?? "—"}</p>
            </div>
            <div className="metric-card">
              <p className="text-xs uppercase tracking-wide text-slate-500">Management interfaces</p>
              <p className="mt-1 text-2xl font-semibold text-slate-50">{summary?.management_interfaces ?? "—"}</p>
            </div>
          </div>

          <Card>
            <CardContent className="space-y-3">
              <div className="flex flex-col gap-2 lg:flex-row lg:flex-wrap lg:items-center">
                <SearchInput value={serviceSearch} onChange={(value) => { setServiceSearch(value); setServicePage(1); }} placeholder="Search service, product or host" />
                <Input aria-label="Port" value={port} onChange={(event) => { setPort(event.target.value.replace(/\D/g, "")); setServicePage(1); }} placeholder="Port" className="lg:w-24" inputMode="numeric" />
                <Select aria-label="Category" value={category} onChange={(event) => { setCategory(event.target.value); setServicePage(1); }} className="lg:w-44">
                  <option value="">All categories</option>
                  {(summary?.by_category ?? []).map((entry) => (
                    <option key={entry.category} value={entry.category}>{titleize(entry.category)}</option>
                  ))}
                </Select>
                <Select aria-label="Risky filter" value={risky} onChange={(event) => { setRisky(event.target.value); setServicePage(1); }} className="lg:w-36">
                  <option value="">Risk: any</option>
                  <option value="true">Risky only</option>
                  <option value="false">Not risky</option>
                </Select>
                <Select aria-label="Unexpected filter" value={unexpected} onChange={(event) => { setUnexpected(event.target.value); setServicePage(1); }} className="lg:w-44">
                  <option value="">Expected: any</option>
                  <option value="true">Unexpected only</option>
                  <option value="false">Expected only</option>
                </Select>
                <Select aria-label="Encryption filter" value={encrypted} onChange={(event) => { setEncrypted(event.target.value); setServicePage(1); }} className="lg:w-40">
                  <option value="">Encryption: any</option>
                  <option value="true">Encrypted</option>
                  <option value="false">Unencrypted</option>
                </Select>
                {serviceSearch || port || category || risky || unexpected || encrypted ? (
                  <Button variant="ghost" size="sm" onClick={() => { setServiceSearch(""); setPort(""); setCategory(""); setRisky(""); setUnexpected(""); setEncrypted(""); setServicePage(1); }}>
                    <RotateCcw aria-hidden="true" className="h-3.5 w-3.5" /> Reset
                  </Button>
                ) : null}
              </div>

              {servicesQuery.isLoading ? (
                <TableLoading columns={7} />
              ) : servicesQuery.isError ? (
                <ErrorState title="Could not load services" message={errorMessage(servicesQuery.error)} onRetry={() => void servicesQuery.refetch()} />
              ) : services.length === 0 ? (
                <EmptyState
                  icon={Server}
                  title="No exposed services recorded"
                  description="Port checks are opt-in, gated by an approved authorization and disabled entirely in safe mode. No service rows means no permitted port scan has run."
                  action={<Link to="/scans"><Button size="sm" variant="ghost"><ShieldAlert className="h-4 w-4" /> Go to scans</Button></Link>}
                />
              ) : (
                <>
                  <div className="overflow-x-auto rounded-md border border-border">
                    <Table>
                      <THead>
                        <Tr>
                          <Th>Host</Th>
                          <Th>Port</Th>
                          <Th>Service</Th>
                          <Th className="hidden lg:table-cell">Product / version</Th>
                          <Th>Flags</Th>
                          <Th className="hidden md:table-cell">Last seen</Th>
                          <Th align="right">Risk level</Th>
                        </Tr>
                      </THead>
                      <TBody>
                        {services.map((service) => (
                          <Tr key={service.id}>
                            <Td>
                              <Link to={`/assets/${service.asset_id}`} className="block max-w-[18rem] truncate font-medium text-slate-200 hover:text-brand-400">
                                {service.host ?? "Unknown host"}
                              </Link>
                            </Td>
                            <Td><span className="num text-sm text-slate-200">{service.port}</span><span className="text-xs text-slate-500">/{service.transport}</span></Td>
                            <Td><span className="text-xs text-slate-300">{service.service_name ?? "unknown"}</span><p className="text-[11px] text-slate-500">{service.protocol_category ? titleize(service.protocol_category) : "Uncategorised"}</p></Td>
                            <Td className="hidden lg:table-cell"><span className="text-xs text-slate-300">{[service.product, service.version].filter(Boolean).join(" ") || "—"}</span></Td>
                            <Td>
                              <div className="flex flex-wrap gap-1">
                                {!service.is_expected ? <Badge tone="high">Unexpected</Badge> : null}
                                {!service.is_encrypted ? <Badge tone="medium">Unencrypted</Badge> : null}
                                {service.is_risky ? <Badge tone={riskTone(service.risk_level)}>Risky</Badge> : null}
                                {service.state !== "open" ? <Badge tone="neutral">{titleize(service.state)}</Badge> : null}
                                {service.is_expected && service.is_encrypted && !service.is_risky && service.state === "open" ? <Badge tone="low">Expected</Badge> : null}
                              </div>
                            </Td>
                            <Td className="hidden md:table-cell"><span className="text-xs text-slate-500">{service.last_seen ? relativeTime(service.last_seen) : "—"}</span></Td>
                            <Td align="right">
                              {service.risk_level ? <Badge tone={riskTone(service.risk_level)}>{titleize(service.risk_level)}</Badge> : <span className="text-xs text-slate-500">—</span>}
                            </Td>
                          </Tr>
                        ))}
                      </TBody>
                    </Table>
                  </div>
                  <Pagination page={servicesData?.page ?? servicePage} total={servicesData?.total} pageSize={servicesData?.page_size ?? servicePageSize} onPageChange={setServicePage} />
                </>
              )}
            </CardContent>
          </Card>
          <p className="mt-4 flex items-center gap-1.5 text-[11px] text-slate-500">
            <ShieldOff aria-hidden="true" className="h-3.5 w-3.5" />
            Service inventory can be demonstration data. Check provenance on the source asset before treating it as live.
          </p>
        </>
      )}
    </div>
  );
}

export default IpsPage;
