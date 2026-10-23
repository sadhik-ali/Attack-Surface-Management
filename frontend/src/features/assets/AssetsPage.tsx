import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import {
  Download,
  FileUp,
  Plus,
  RotateCcw,
  ShieldCheck,
  Upload,
} from "lucide-react";

import { PageHeader } from "@/components/common/PageHeader";
import { RiskBadge, SourceBadge, StatusBadge } from "@/components/common/Badges";
import { SearchInput, TableLoading } from "@/components/common/TableState";
import {
  Badge,
  Button,
  Card,
  CardContent,
  EmptyState,
  ErrorState,
  Input,
  Modal,
  Pagination,
  Select,
  Table,
  TBody,
  Td,
  Th,
  THead,
  Tr,
  useToast,
} from "@/components/ui";
import { apiRequest, downloadFile, errorMessage, saveBlob } from "@/lib/api";
import type { Asset, CsvImportResult, Page } from "@/lib/apiTypes";
import { titleize } from "@/lib/labels";
import { formatDate, formatNumber, relativeTime } from "@/lib/utils";
import { useAuth } from "@/context/AuthProvider";

const ASSET_TYPES = [
  "domain",
  "subdomain",
  "ip_address",
  "web_application",
  "api_endpoint",
  "cloud_resource",
  "network_service",
];
const CRITICALITIES = ["business_critical", "high", "medium", "low", "unknown"];
const EXPOSURES = ["internet_facing", "partner_facing", "internal", "unknown"];
const STATUSES = ["new", "active", "changed", "retired"];
const SORT_KEYS = new Set(["name", "risk_score", "last_seen", "first_seen", "asset_type", "criticality", "status"]);

type RegisterForm = {
  name: string;
  asset_type: string;
  criticality: string;
  exposure: string;
  environment: string;
  owner: string;
  url: string;
  description: string;
  tags: string;
};

const EMPTY_REGISTER: RegisterForm = {
  name: "",
  asset_type: "domain",
  criticality: "unknown",
  exposure: "internet_facing",
  environment: "production",
  owner: "",
  url: "",
  description: "",
  tags: "",
};

export function AssetsPage() {
  const { selectedCompanyId, can } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const [search, setSearch] = useState("");
  const [assetType, setAssetType] = useState("");
  const [status, setStatus] = useState("");
  const [criticality, setCriticality] = useState("");
  const [exposure, setExposure] = useState("");
  const [hasFindings, setHasFindings] = useState("");
  const [sort, setSort] = useState("risk_score");
  const [order, setOrder] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);

  const [registerOpen, setRegisterOpen] = useState(false);
  const [registerForm, setRegisterForm] = useState<RegisterForm>(EMPTY_REGISTER);
  const [registerError, setRegisterError] = useState<string | null>(null);

  const [importOpen, setImportOpen] = useState(false);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [dryRun, setDryRun] = useState(true);
  const [importResult, setImportResult] = useState<CsvImportResult | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  const filters = {
    q: search.trim() || undefined,
    asset_type: assetType || undefined,
    status: status || undefined,
    criticality: criticality || undefined,
    exposure: exposure || undefined,
    has_findings: hasFindings === "" ? undefined : hasFindings === "true",
  };

  const assetsQuery = useQuery({
    queryKey: ["assets", selectedCompanyId, filters, sort, order, page, pageSize],
    queryFn: () =>
      apiRequest<Page<Asset>>(`/companies/${selectedCompanyId}/assets`, {
        params: { ...filters, sort, order, page, page_size: pageSize },
      }),
    enabled: Boolean(selectedCompanyId),
    placeholderData: (previous) => previous,
  });

  const registerMutation = useMutation({
    mutationFn: (form: RegisterForm) =>
      apiRequest<Asset>(`/companies/${selectedCompanyId}/assets`, {
        method: "POST",
        body: {
          name: form.name.trim(),
          asset_type: form.asset_type,
          criticality: form.criticality,
          exposure: form.exposure,
          environment: form.environment.trim() || null,
          owner: form.owner.trim() || null,
          url: form.url.trim() || null,
          description: form.description.trim() || null,
          tags: form.tags
            .split(",")
            .map((tag) => tag.trim())
            .filter(Boolean),
        },
      }),
    onSuccess: async (asset) => {
      toast({ title: "Asset registered", description: asset.name, variant: "success" });
      setRegisterOpen(false);
      setRegisterForm(EMPTY_REGISTER);
      await queryClient.invalidateQueries({ queryKey: ["assets"] });
    },
    onError: (error) => setRegisterError(errorMessage(error)),
  });

  const importMutation = useMutation({
    mutationFn: async (preview: boolean) => {
      if (!importFile) throw new Error("Choose a CSV file first");
      const form = new FormData();
      form.append("file", importFile);
      return apiRequest<CsvImportResult>(`/companies/${selectedCompanyId}/assets/import`, {
        method: "POST",
        rawBody: form,
        params: preview ? { dry_run: true } : undefined,
      });
    },
    onSuccess: async (result) => {
      setImportResult(result);
      if (!result.dry_run) {
        await queryClient.invalidateQueries({ queryKey: ["assets"] });
        toast({
          title: "Import complete",
          description: `${result.created} created, ${result.updated} updated, ${result.skipped} skipped.`,
          variant: "success",
        });
      }
    },
    onError: (error) => setImportError(errorMessage(error)),
  });

  const activeFilterCount = [assetType, status, criticality, exposure, hasFindings].filter(Boolean).length;
  const resetFilters = () => {
    setAssetType("");
    setStatus("");
    setCriticality("");
    setExposure("");
    setHasFindings("");
    setSearch("");
    setPage(1);
  };

  const toggleSort = (key: string) => {
    if (!SORT_KEYS.has(key)) return;
    if (sort === key) {
      setOrder((current) => (current === "desc" ? "asc" : "desc"));
    } else {
      setSort(key);
      setOrder(key === "name" ? "asc" : "desc");
    }
    setPage(1);
  };

  const exportCsv = async () => {
    if (!selectedCompanyId) return;
    setExporting(true);
    try {
      const { blob, filename } = await downloadFile(`/companies/${selectedCompanyId}/assets/export`, {
        asset_type: assetType || undefined,
      });
      saveBlob(blob, filename ?? "assets.csv");
      toast({ title: "Export ready", description: "Asset inventory CSV downloaded.", variant: "success" });
    } catch (error) {
      toast({ title: "Export failed", description: errorMessage(error), variant: "error" });
    } finally {
      setExporting(false);
    }
  };

  const data = assetsQuery.data;
  const items = data?.items ?? [];
  const columns = 8;

  const pageDescription = useMemo(() => {
    if (!data) return "Every domain, host, IP, endpoint and cloud resource in this tenant.";
    return `${formatNumber(data.total)} matching asset${data.total === 1 ? "" : "s"} in this tenant.`;
  }, [data]);

  if (!selectedCompanyId) return null;

  return (
    <div>
      <PageHeader
        title="Asset inventory"
        description={pageDescription}
        actions={
          <>
            {can("report:export") ? (
              <Button variant="ghost" size="sm" onClick={() => void exportCsv()} disabled={exporting}>
                <Download aria-hidden="true" className="h-4 w-4" />
                {exporting ? "Exporting…" : "Export CSV"}
              </Button>
            ) : null}
            {can("asset:import") ? (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setImportError(null);
                  setImportResult(null);
                  setImportOpen(true);
                }}
              >
                <FileUp aria-hidden="true" className="h-4 w-4" />
                Import CSV
              </Button>
            ) : null}
            {can("asset:write") ? (
              <Button
                size="sm"
                onClick={() => {
                  setRegisterError(null);
                  setRegisterOpen(true);
                }}
              >
                <Plus aria-hidden="true" className="h-4 w-4" />
                Register asset
              </Button>
            ) : null}
          </>
        }
      />

      <Card>
        <CardContent className="space-y-3">
          <div className="flex flex-col gap-2 lg:flex-row lg:flex-wrap lg:items-center">
            <SearchInput value={search} onChange={(value) => { setSearch(value); setPage(1); }} placeholder="Search name or owner" />
            <Select
              aria-label="Filter by asset type"
              value={assetType}
              onChange={(event) => { setAssetType(event.target.value); setPage(1); }}
              className="lg:w-40"
            >
              <option value="">All types</option>
              {ASSET_TYPES.map((type) => (
                <option key={type} value={type}>{titleize(type)}</option>
              ))}
            </Select>
            <Select
              aria-label="Filter by status"
              value={status}
              onChange={(event) => { setStatus(event.target.value); setPage(1); }}
              className="lg:w-36"
            >
              <option value="">All statuses</option>
              {STATUSES.map((item) => (
                <option key={item} value={item}>{titleize(item)}</option>
              ))}
            </Select>
            <Select
              aria-label="Filter by criticality"
              value={criticality}
              onChange={(event) => { setCriticality(event.target.value); setPage(1); }}
              className="lg:w-40"
            >
              <option value="">Any criticality</option>
              {CRITICALITIES.map((item) => (
                <option key={item} value={item}>{titleize(item)}</option>
              ))}
            </Select>
            <Select
              aria-label="Filter by exposure"
              value={exposure}
              onChange={(event) => { setExposure(event.target.value); setPage(1); }}
              className="lg:w-40"
            >
              <option value="">Any exposure</option>
              {EXPOSURES.map((item) => (
                <option key={item} value={item}>{titleize(item)}</option>
              ))}
            </Select>
            <Select
              aria-label="Filter by findings"
              value={hasFindings}
              onChange={(event) => { setHasFindings(event.target.value); setPage(1); }}
              className="lg:w-40"
            >
              <option value="">Findings: any</option>
              <option value="true">With open findings</option>
              <option value="false">Without findings</option>
            </Select>
            {activeFilterCount > 0 || search ? (
              <Button variant="ghost" size="sm" onClick={resetFilters}>
                <RotateCcw aria-hidden="true" className="h-3.5 w-3.5" />
                Reset
                <Badge tone="neutral">{activeFilterCount}</Badge>
              </Button>
            ) : null}
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
            <span>
              {data ? (
                <>
                  Page {data.page} of {data.pages} · {formatNumber(data.total)} records
                </>
              ) : (
                "Loading inventory…"
              )}
            </span>
            <label className="flex items-center gap-2">
              Rows per page
              <Select
                aria-label="Rows per page"
                value={String(pageSize)}
                onChange={(event) => { setPageSize(Number(event.target.value)); setPage(1); }}
                className="w-20"
              >
                {[10, 25, 50, 100].map((size) => (
                  <option key={size} value={size}>{size}</option>
                ))}
              </Select>
            </label>
          </div>

          {assetsQuery.isLoading ? (
            <TableLoading columns={columns} />
          ) : assetsQuery.isError ? (
            <ErrorState
              title="Could not load assets"
              message={errorMessage(assetsQuery.error)}
              onRetry={() => void assetsQuery.refetch()}
            />
          ) : items.length === 0 ? (
            <EmptyState
              icon={ShieldCheck}
              title={search || activeFilterCount > 0 ? "No assets match these filters" : "No assets in inventory"}
              description={
                search || activeFilterCount > 0
                  ? "Adjust or clear the filters to widen the search."
                  : "Register an asset manually, import a CSV, or run an authorized discovery scan."
              }
              action={
                search || activeFilterCount > 0 ? (
                  <Button variant="ghost" size="sm" onClick={resetFilters}>Clear filters</Button>
                ) : can("asset:write") ? (
                  <Button size="sm" onClick={() => setRegisterOpen(true)}>
                    <Plus aria-hidden="true" className="h-4 w-4" /> Register asset
                  </Button>
                ) : null
              }
            />
          ) : (
            <>
              <div className="overflow-x-auto rounded-md border border-border">
                <Table>
                  <THead>
                    <Tr>
                      <Th sortable sortDirection={sort === "name" ? order : undefined} onSort={() => toggleSort("name")}>Asset</Th>
                      <Th sortable sortDirection={sort === "asset_type" ? order : undefined} onSort={() => toggleSort("asset_type")}>Type</Th>
                      <Th>Status</Th>
                      <Th className="hidden lg:table-cell">Criticality</Th>
                      <Th className="hidden xl:table-cell">Exposure</Th>
                      <Th sortable align="right" sortDirection={sort === "risk_score" ? order : undefined} onSort={() => toggleSort("risk_score")}>Risk</Th>
                      <Th align="right">Findings</Th>
                      <Th className="hidden md:table-cell">Source</Th>
                      <Th sortable className="hidden lg:table-cell" sortDirection={sort === "last_seen" ? order : undefined} onSort={() => toggleSort("last_seen")}>Last seen</Th>
                    </Tr>
                  </THead>
                  <TBody>
                    {items.map((asset) => (
                      <Tr
                        key={asset.id}
                        className="cursor-pointer"
                        onClick={() => navigate(`/assets/${asset.id}`)}
                      >
                        <Td>
                          <Link
                            to={`/assets/${asset.id}`}
                            onClick={(event) => event.stopPropagation()}
                            className="block max-w-[22rem] truncate font-medium text-slate-200 hover:text-brand-400"
                            title={asset.name}
                          >
                            {asset.name}
                          </Link>
                          <p className="mt-0.5 truncate text-[11px] text-slate-500">
                            {asset.environment ? `${titleize(asset.environment)} · ` : ""}
                            {asset.owner ?? "Unassigned owner"}
                          </p>
                        </Td>
                        <Td><span className="text-xs text-slate-300">{titleize(asset.asset_type)}</span></Td>
                        <Td><StatusBadge status={asset.status} /></Td>
                        <Td className="hidden lg:table-cell"><span className="text-xs text-slate-300">{titleize(asset.criticality)}</span></Td>
                        <Td className="hidden xl:table-cell"><span className="text-xs text-slate-400">{titleize(asset.exposure)}</span></Td>
                        <Td align="right"><RiskBadge score={asset.risk_score} classification={asset.risk_classification} /></Td>
                        <Td align="right">
                          {asset.open_findings > 0 ? (
                            <Badge tone={asset.critical_findings > 0 ? "critical" : asset.high_findings > 0 ? "high" : "medium"}>
                              <span className="num">{asset.open_findings}</span>
                            </Badge>
                          ) : (
                            <span className="text-xs text-slate-500">0</span>
                          )}
                        </Td>
                        <Td className="hidden md:table-cell"><SourceBadge source={asset.source} provenance={asset.provenance} /></Td>
                        <Td className="hidden lg:table-cell">
                          <span className="text-xs text-slate-400" title={asset.last_seen ? formatDate(asset.last_seen) : undefined}>
                            {asset.last_seen ? relativeTime(asset.last_seen) : "—"}
                          </span>
                        </Td>
                      </Tr>
                    ))}
                  </TBody>
                </Table>
              </div>
              <Pagination
                page={data?.page ?? page}
                total={data?.total}
                pageSize={data?.page_size ?? pageSize}
                onPageChange={setPage}
              />
            </>
          )}
        </CardContent>
      </Card>

      <Modal
        open={registerOpen}
        onClose={() => setRegisterOpen(false)}
        title="Register an asset"
        description="Manual registration records ownership context. It does not verify the asset or probe it."
        size="lg"
        footer={
          <>
            <Button variant="ghost" size="sm" onClick={() => setRegisterOpen(false)} disabled={registerMutation.isPending}>Cancel</Button>
            <Button
              size="sm"
              onClick={() => {
                setRegisterError(null);
                if (!registerForm.name.trim()) {
                  setRegisterError("An asset name or identifier is required");
                  return;
                }
                registerMutation.mutate(registerForm);
              }}
              disabled={registerMutation.isPending}
            >
              {registerMutation.isPending ? "Registering…" : "Register asset"}
            </Button>
          </>
        }
      >
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            setRegisterError(null);
            if (!registerForm.name.trim()) {
              setRegisterError("An asset name or identifier is required");
              return;
            }
            registerMutation.mutate(registerForm);
          }}
        >
          {registerError ? (
            <p role="alert" className="rounded-md border border-critical/30 bg-critical/10 px-3 py-2 text-xs text-critical">{registerError}</p>
          ) : null}
          <div className="grid gap-4 sm:grid-cols-2">
            <Input
              label="Name or identifier"
              required
              value={registerForm.name}
              onChange={(event) => setRegisterForm((current) => ({ ...current, name: event.target.value }))}
              placeholder="app.acme.example or 203.0.113.10"
              hint="Domain, IP, URL or resource identifier."
            />
            <Select
              label="Asset type"
              value={registerForm.asset_type}
              onChange={(event) => setRegisterForm((current) => ({ ...current, asset_type: event.target.value }))}
            >
              {ASSET_TYPES.map((type) => (
                <option key={type} value={type}>{titleize(type)}</option>
              ))}
            </Select>
            <Select
              label="Criticality"
              value={registerForm.criticality}
              onChange={(event) => setRegisterForm((current) => ({ ...current, criticality: event.target.value }))}
            >
              {CRITICALITIES.map((item) => (
                <option key={item} value={item}>{titleize(item)}</option>
              ))}
            </Select>
            <Select
              label="Exposure"
              value={registerForm.exposure}
              onChange={(event) => setRegisterForm((current) => ({ ...current, exposure: event.target.value }))}
            >
              {EXPOSURES.map((item) => (
                <option key={item} value={item}>{titleize(item)}</option>
              ))}
            </Select>
            <Input
              label="Environment"
              value={registerForm.environment}
              onChange={(event) => setRegisterForm((current) => ({ ...current, environment: event.target.value }))}
              placeholder="production, staging…"
            />
            <Input
              label="Owner"
              value={registerForm.owner}
              onChange={(event) => setRegisterForm((current) => ({ ...current, owner: event.target.value }))}
              placeholder="Team or individual"
            />
            <Input
              label="URL"
              value={registerForm.url}
              onChange={(event) => setRegisterForm((current) => ({ ...current, url: event.target.value }))}
              placeholder="https://app.acme.example"
              hint="Optional for web applications and API endpoints."
            />
            <Input
              label="Tags"
              value={registerForm.tags}
              onChange={(event) => setRegisterForm((current) => ({ ...current, tags: event.target.value }))}
              placeholder="crown-jewel, pci"
              hint="Comma separated."
            />
          </div>
          <Input
            label="Description"
            value={registerForm.description}
            onChange={(event) => setRegisterForm((current) => ({ ...current, description: event.target.value }))}
            placeholder="Business context, data handled, notes…"
          />
          <p className="rounded-md bg-surface-raised/60 px-3 py-2 text-[11px] leading-relaxed text-slate-500">
            New assets start with no observed services or certificates. Those are only added by an authorized scan.
          </p>
          <button type="submit" className="hidden" aria-hidden="true" tabIndex={-1} />
        </form>
      </Modal>

      <Modal
        open={importOpen}
        onClose={() => setImportOpen(false)}
        title="Import assets from CSV"
        description="Required columns: name and type. Optional: criticality, exposure, owner, environment, description, url, tags (semicolon separated)."
        footer={
          <>
            <Button variant="ghost" size="sm" onClick={() => setImportOpen(false)} disabled={importMutation.isPending}>Close</Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                if (!importFile) {
                  setImportError("Choose a CSV file first");
                  return;
                }
                setImportError(null);
                importMutation.mutate(dryRun);
              }}
              disabled={importMutation.isPending || !importFile}
            >
              <Upload aria-hidden="true" className="h-4 w-4" />
              {importMutation.isPending ? "Checking…" : "Preview import"}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-300" htmlFor="csv-file">CSV file</label>
            <input
              id="csv-file"
              type="file"
              accept=".csv,text/csv"
              onChange={(event) => {
                setImportFile(event.target.files?.[0] ?? null);
                setImportResult(null);
                setImportError(null);
              }}
              className="block w-full cursor-pointer rounded-md border border-border bg-surface-raised px-3 py-2 text-xs text-slate-300 file:mr-3 file:rounded file:border-0 file:bg-brand-500/15 file:px-2.5 file:py-1 file:text-xs file:font-medium file:text-brand-300 hover:file:bg-brand-500/25"
            />
            <p className="mt-1 text-[11px] text-slate-500">UTF-8 encoded, maximum 2 MB. Existing assets are matched by identifier and updated.</p>
          </div>

          <label className="flex items-start gap-2 rounded-md border border-border bg-surface-raised/50 px-3 py-2.5 text-xs text-slate-300">
            <input
              type="checkbox"
              checked={dryRun}
              onChange={(event) => { setDryRun(event.target.checked); setImportResult(null); }}
              className="mt-0.5"
            />
            <span>
              <span className="font-medium text-slate-200">Preview only (dry run)</span>
              <span className="block text-[11px] text-slate-500">
                Recommended first. Counts what would be created or updated without writing any rows.
              </span>
            </span>
          </label>

          {importError ? (
            <p role="alert" className="rounded-md border border-critical/30 bg-critical/10 px-3 py-2 text-xs text-critical">{importError}</p>
          ) : null}

          {importResult ? (
            <div className="rounded-md border border-border bg-surface-raised/50 p-3">
              <p className="text-xs font-medium text-slate-200">
                {importResult.dry_run ? "Dry-run summary (nothing written)" : "Import summary"}
              </p>
              <div className="mt-2 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
                <div><span className="block text-slate-500">Rows</span><span className="num text-slate-200">{importResult.total_rows}</span></div>
                <div><span className="block text-slate-500">Create</span><span className="num text-low">{importResult.created}</span></div>
                <div><span className="block text-slate-500">Update</span><span className="num text-brand-400">{importResult.updated}</span></div>
                <div><span className="block text-slate-500">Skipped</span><span className="num text-slate-400">{importResult.skipped}</span></div>
              </div>
              {importResult.errors.length > 0 ? (
                <ul className="mt-2 max-h-32 space-y-1 overflow-y-auto text-[11px] text-critical">
                  {importResult.errors.slice(0, 20).map((entry) => (
                    <li key={`${entry.row}-${entry.message}`}>Row {entry.row}: {entry.message}</li>
                  ))}
                </ul>
              ) : null}
              {importResult.dry_run ? (
                <Button
                  size="sm"
                  className="mt-3"
                  onClick={() => {
                    setDryRun(false);
                    setImportError(null);
                    importMutation.mutate(false);
                  }}
                  disabled={importMutation.isPending}
                >
                  Apply this import
                </Button>
              ) : null}
            </div>
          ) : null}
        </div>
      </Modal>
    </div>
  );
}

export default AssetsPage;
