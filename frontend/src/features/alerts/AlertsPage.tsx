import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BellRing,
  Check,
  CheckCheck,
  Inbox,
  Settings2,
  ShieldAlert,
  XCircle,
} from "lucide-react";

import { PageHeader } from "@/components/common/PageHeader";
import { SeverityBadge, StatusBadge } from "@/components/common/Badges";
import { SearchInput, TableLoading } from "@/components/common/TableState";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Checkbox,
  ConfirmDialog,
  EmptyState,
  ErrorState,
  Input,
  Modal,
  Pagination,
  Select,
  Spinner,
  Table,
  TBody,
  Td,
  Th,
  THead,
  Tr,
  Tabs,
  useToast,
} from "@/components/ui";
import { apiRequest, errorMessage } from "@/lib/api";
import type {
  Alert,
  AlertCounts,
  AlertPreference,
  Notification,
  Page,
} from "@/lib/apiTypes";
import { severityLabel, titleize } from "@/lib/labels";
import { cn, formatDateTime, formatNumber, relativeTime } from "@/lib/utils";
import { useAuth } from "@/context/AuthProvider";

const SEVERITIES = ["critical", "high", "medium", "low", "informational"];

const TABS = [
  {
    value: "alerts",
    label: "Alert inbox",
    icon: <BellRing aria-hidden="true" className="h-3.5 w-3.5" />,
  },
  {
    value: "notifications",
    label: "Notifications",
    icon: <Inbox aria-hidden="true" className="h-3.5 w-3.5" />,
  },
  {
    value: "preferences",
    label: "Preferences",
    icon: <Settings2 aria-hidden="true" className="h-3.5 w-3.5" />,
  },
] as const;

type TabValue = (typeof TABS)[number]["value"];

type PreferenceForm = {
  min_severity: string;
  channels: string[];
  muted_types: string[];
  daily_digest: boolean;
};

const EMPTY_PREFERENCE: PreferenceForm = {
  min_severity: "low",
  channels: ["in_app"],
  muted_types: [],
  daily_digest: false,
};

export function AlertsPage() {
  const { selectedCompanyId, can, enums } = useAuth();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [searchParams, setSearchParams] = useSearchParams();

  const tabParam = searchParams.get("tab");
  const tab: TabValue =
    tabParam === "notifications" || tabParam === "preferences"
      ? tabParam
      : "alerts";
  const setTab = (value: string) => {
    const next = new URLSearchParams(searchParams);
    if (value === "alerts") next.delete("tab");
    else next.set("tab", value);
    setSearchParams(next, { replace: true });
  };

  const [search, setSearch] = useState("");
  const [severity, setSeverity] = useState("");
  const [alertType, setAlertType] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize] = useState(25);
  const [selected, setSelected] = useState<Alert | null>(null);
  const [ackNote, setAckNote] = useState("");
  const [dismissTarget, setDismissTarget] = useState<Alert | null>(null);
  const [dismissReason, setDismissReason] = useState("");
  const [resolveTarget, setResolveTarget] = useState<Alert | null>(null);

  const [notificationPage, setNotificationPage] = useState(1);
  const [unreadOnly, setUnreadOnly] = useState(false);

  const [preferenceForm, setPreferenceForm] =
    useState<PreferenceForm>(EMPTY_PREFERENCE);

  const filters = {
    q: search.trim() || undefined,
    severity: severity || undefined,
    alert_type: alertType || undefined,
    status: status && status !== "all" ? status : undefined,
    include_resolved: status === "all" ? true : undefined,
  };

  const countsQuery = useQuery({
    queryKey: ["alert-counts", selectedCompanyId],
    queryFn: () =>
      apiRequest<AlertCounts>(`/companies/${selectedCompanyId}/alerts/counts`),
    enabled: Boolean(selectedCompanyId),
    refetchInterval: 60_000,
  });

  const alertsQuery = useQuery({
    queryKey: ["alerts", selectedCompanyId, filters, page, pageSize],
    queryFn: () =>
      apiRequest<Page<Alert>>(`/companies/${selectedCompanyId}/alerts`, {
        params: {
          ...filters,
          page,
          page_size: pageSize,
          sort: "occurred_at",
          order: "desc",
        },
      }),
    enabled: Boolean(selectedCompanyId) && tab === "alerts",
    placeholderData: (previous) => previous,
  });

  const notificationsQuery = useQuery({
    queryKey: ["notifications", "centre", notificationPage, unreadOnly],
    queryFn: () =>
      apiRequest<Page<Notification>>("/notifications", {
        params: {
          page: notificationPage,
          page_size: 25,
          unread_only: unreadOnly || undefined,
        },
      }),
    enabled: tab === "notifications",
  });

  const preferencesQuery = useQuery({
    queryKey: ["alert-preferences", selectedCompanyId],
    queryFn: () =>
      apiRequest<AlertPreference>(
        `/companies/${selectedCompanyId}/alert-preferences`,
      ),
    enabled: Boolean(selectedCompanyId) && tab === "preferences",
  });

  useEffect(() => {
    if (!preferencesQuery.data) return;
    setPreferenceForm({
      min_severity: preferencesQuery.data.min_severity,
      channels: preferencesQuery.data.channels,
      muted_types: preferencesQuery.data.muted_types,
      daily_digest: preferencesQuery.data.daily_digest,
    });
  }, [preferencesQuery.data]);

  useEffect(() => {
    setAckNote("");
  }, [selected?.id]);

  const refreshLists = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["alerts"] }),
      queryClient.invalidateQueries({ queryKey: ["alert-counts", selectedCompanyId] }),
      queryClient.invalidateQueries({ queryKey: ["notifications"] }),
      queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
    ]);
  };

  const ackMutation = useMutation({
    mutationFn: ({ id, note }: { id: string; note: string }) =>
      apiRequest<Alert>(
        `/companies/${selectedCompanyId}/alerts/${id}/acknowledge`,
        { method: "POST", body: { note: note.trim() || null } },
      ),
    onSuccess: async (updated) => {
      setSelected(updated);
      setAckNote("");
      toast({ title: "Alert acknowledged", variant: "success" });
      await refreshLists();
    },
    onError: (error) =>
      toast({
        title: "Could not acknowledge alert",
        description: errorMessage(error),
        variant: "error",
      }),
  });

  const dismissMutation = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      apiRequest<Alert>(
        `/companies/${selectedCompanyId}/alerts/${id}/dismiss`,
        { method: "POST", body: { reason } },
      ),
    onSuccess: async (updated) => {
      setSelected(updated);
      setDismissTarget(null);
      setDismissReason("");
      toast({ title: "Alert dismissed", variant: "success" });
      await refreshLists();
    },
    onError: (error) =>
      toast({
        title: "Could not dismiss alert",
        description: errorMessage(error),
        variant: "error",
      }),
  });

  const resolveMutation = useMutation({
    mutationFn: (id: string) =>
      apiRequest<Alert>(
        `/companies/${selectedCompanyId}/alerts/${id}/resolve`,
        { method: "POST" },
      ),
    onSuccess: async (updated) => {
      setSelected(updated);
      setResolveTarget(null);
      toast({ title: "Alert resolved", variant: "success" });
      await refreshLists();
    },
    onError: (error) =>
      toast({
        title: "Could not resolve alert",
        description: errorMessage(error),
        variant: "error",
      }),
  });

  const markOneMutation = useMutation({
    mutationFn: (notificationId: string) =>
      apiRequest<Notification>(`/notifications/${notificationId}/read`, {
        method: "POST",
      }),
    onSuccess: async () => {
      await refreshLists();
    },
    onError: (error) =>
      toast({
        title: "Could not mark notification read",
        description: errorMessage(error),
        variant: "error",
      }),
  });

  const markAllMutation = useMutation({
    mutationFn: () =>
      apiRequest<{ message: string }>("/notifications/read-all", {
        method: "POST",
      }),
    onSuccess: async (response) => {
      toast({ title: response.message, variant: "success" });
      await refreshLists();
    },
    onError: (error) =>
      toast({
        title: "Could not mark notifications read",
        description: errorMessage(error),
        variant: "error",
      }),
  });

  const preferenceMutation = useMutation({
    mutationFn: (form: PreferenceForm) =>
      apiRequest<AlertPreference>(
        `/companies/${selectedCompanyId}/alert-preferences`,
        {
          method: "PUT",
          body: {
            min_severity: form.min_severity,
            channels: form.channels,
            muted_types: form.muted_types,
            daily_digest: form.daily_digest,
          },
        },
      ),
    onSuccess: async () => {
      toast({ title: "Alert preferences saved", variant: "success" });
      await queryClient.invalidateQueries({
        queryKey: ["alert-preferences", selectedCompanyId],
      });
    },
    onError: (error) =>
      toast({
        title: "Could not save preferences",
        description: errorMessage(error),
        variant: "error",
      }),
  });

  if (!selectedCompanyId) return null;

  const counts = countsQuery.data;
  const alerts = alertsQuery.data;
  const alertItems = alerts?.items ?? [];
  const notifications = notificationsQuery.data;
  const activeFilterCount = [search, severity, alertType, status].filter(Boolean).length;

  const resetFilters = () => {
    setSearch("");
    setSeverity("");
    setAlertType("");
    setStatus("");
    setPage(1);
  };

  const toggleMutedType = (value: string) => {
    setPreferenceForm((current) => ({
      ...current,
      muted_types: current.muted_types.includes(value)
        ? current.muted_types.filter((entry) => entry !== value)
        : [...current.muted_types, value],
    }));
  };

  return (
    <div>
      <PageHeader
        title="Alerts & notifications"
        description="Actionable security events, the in-app notification centre and per-user routing preferences. Acknowledgement records review; dismissal records why an alert was set aside."
      />

      <div className="mb-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <div className="metric-card">
          <div className="flex items-center gap-2 text-xs text-slate-500"><BellRing className="h-3.5 w-3.5" /> New alerts</div>
          <p className="mt-1 text-2xl font-semibold text-brand-400">{counts ? formatNumber(counts.new) : "—"}</p>
        </div>
        <div className="metric-card">
          <div className="flex items-center gap-2 text-xs text-slate-500"><Check className="h-3.5 w-3.5" /> Acknowledged</div>
          <p className="mt-1 text-2xl font-semibold text-slate-50">{counts ? formatNumber(counts.acknowledged) : "—"}</p>
        </div>
        <div className="metric-card">
          <div className="flex items-center gap-2 text-xs text-slate-500"><ShieldAlert className="h-3.5 w-3.5" /> Critical active</div>
          <p className="mt-1 text-2xl font-semibold text-critical">{counts ? formatNumber(counts.critical) : "—"}</p>
        </div>
        <div className="metric-card">
          <div className="flex items-center gap-2 text-xs text-slate-500"><ShieldAlert className="h-3.5 w-3.5" /> High active</div>
          <p className="mt-1 text-2xl font-semibold text-high">{counts ? formatNumber(counts.high) : "—"}</p>
        </div>
        <div className="metric-card">
          <div className="flex items-center gap-2 text-xs text-slate-500"><Inbox className="h-3.5 w-3.5" /> Unread notifications</div>
          <p className="mt-1 text-2xl font-semibold text-slate-50">{counts ? formatNumber(counts.unread_notifications) : "—"}</p>
        </div>
      </div>

      <Tabs
        value={tab}
        onValueChange={setTab}
        items={TABS.map((item) => ({
          value: item.value,
          label: item.label,
          icon: item.icon,
          content: null,
        }))}
        className="mb-4"
      />

      {tab === "alerts" ? (
        <Card>
          <CardContent className="space-y-3">
            <div className="flex flex-col gap-2 xl:flex-row xl:flex-wrap xl:items-center">
              <SearchInput
                value={search}
                onChange={(value) => {
                  setSearch(value);
                  setPage(1);
                }}
                placeholder="Search alerts"
              />
              <Select
                aria-label="Status"
                value={status}
                onChange={(event) => {
                  setStatus(event.target.value);
                  setPage(1);
                }}
                className="xl:w-44"
              >
                <option value="">Active (new + acknowledged)</option>
                <option value="new">New</option>
                <option value="acknowledged">Acknowledged</option>
                <option value="dismissed">Dismissed</option>
                <option value="resolved">Resolved</option>
                <option value="all">All statuses</option>
              </Select>
              <Select
                aria-label="Severity"
                value={severity}
                onChange={(event) => {
                  setSeverity(event.target.value);
                  setPage(1);
                }}
                className="xl:w-36"
              >
                <option value="">Any severity</option>
                {SEVERITIES.map((value) => (
                  <option key={value} value={value}>{severityLabel(value)}</option>
                ))}
              </Select>
              <Select
                aria-label="Alert type"
                value={alertType}
                onChange={(event) => {
                  setAlertType(event.target.value);
                  setPage(1);
                }}
                className="xl:w-56"
              >
                <option value="">All alert types</option>
                {(enums?.alert_types ?? []).map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </Select>
              {activeFilterCount > 0 ? (
                <Button variant="ghost" size="sm" onClick={resetFilters}>
                  Reset <Badge tone="neutral">{activeFilterCount}</Badge>
                </Button>
              ) : null}
            </div>

            {alertsQuery.isLoading ? (
              <TableLoading columns={7} />
            ) : alertsQuery.isError ? (
              <ErrorState
                title="Could not load alerts"
                message={errorMessage(alertsQuery.error)}
                onRetry={() => void alertsQuery.refetch()}
              />
            ) : alertItems.length === 0 ? (
              <EmptyState
                icon={BellRing}
                title={activeFilterCount > 0 ? "No alerts match these filters" : "No active alerts"}
                description={
                  activeFilterCount > 0
                    ? "Clear the filters to widen the search."
                    : "Alerts appear when a discovery run or finding produces a security-relevant event. This does not mean the estate is risk-free."
                }
                action={
                  activeFilterCount > 0 ? (
                    <Button variant="ghost" size="sm" onClick={resetFilters}>Clear filters</Button>
                  ) : null
                }
              />
            ) : (
              <>
                <div className="overflow-x-auto rounded-md border border-border">
                  <Table>
                    <THead>
                      <Tr>
                        <Th>Alert</Th>
                        <Th>Severity</Th>
                        <Th className="hidden lg:table-cell">Type</Th>
                        <Th className="hidden xl:table-cell">Asset</Th>
                        <Th>Status</Th>
                        <Th className="hidden lg:table-cell">Occurrences</Th>
                        <Th>Occurred</Th>
                      </Tr>
                    </THead>
                    <TBody>
                      {alertItems.map((alert) => (
                        <Tr
                          key={alert.id}
                          className="cursor-pointer"
                          onClick={() => setSelected(alert)}
                        >
                          <Td>
                            <p className="max-w-[24rem] truncate font-medium text-slate-200" title={alert.title}>
                              {alert.title}
                            </p>
                            <p className="max-w-[24rem] truncate text-[11px] text-slate-500" title={alert.message}>
                              {alert.message}
                            </p>
                          </Td>
                          <Td><SeverityBadge severity={alert.severity} /></Td>
                          <Td className="hidden lg:table-cell">
                            <span className="text-xs text-slate-400">{titleize(alert.alert_type)}</span>
                          </Td>
                          <Td className="hidden xl:table-cell">
                            {alert.asset_id ? (
                              <Link
                                to={`/assets/${alert.asset_id}`}
                                onClick={(event) => event.stopPropagation()}
                                className="block max-w-[12rem] truncate text-xs text-slate-300 hover:text-brand-400"
                              >
                                {alert.asset_name ?? "asset"}
                              </Link>
                            ) : (
                              <span className="text-xs text-slate-500">—</span>
                            )}
                          </Td>
                          <Td><StatusBadge status={alert.status} /></Td>
                          <Td className="hidden lg:table-cell">
                            <span className="num text-xs text-slate-400">{alert.occurrence_count}</span>
                          </Td>
                          <Td>
                            <span className="text-xs text-slate-400" title={formatDateTime(alert.occurred_at)}>
                              {relativeTime(alert.occurred_at)}
                            </span>
                          </Td>
                        </Tr>
                      ))}
                    </TBody>
                  </Table>
                </div>
                <Pagination
                  page={alerts?.page ?? page}
                  total={alerts?.total}
                  pageSize={alerts?.page_size ?? pageSize}
                  onPageChange={setPage}
                />
              </>
            )}
          </CardContent>
        </Card>
      ) : null}

      {tab === "notifications" ? (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between gap-3">
            <CardTitle>In-app notification centre</CardTitle>
            <div className="flex items-center gap-2">
              <Checkbox
                label="Unread only"
                checked={unreadOnly}
                onChange={(event) => {
                  setUnreadOnly(event.target.checked);
                  setNotificationPage(1);
                }}
              />
              <Button
                variant="ghost"
                size="sm"
                onClick={() => markAllMutation.mutate()}
                disabled={markAllMutation.isPending}
              >
                <CheckCheck aria-hidden="true" className="h-4 w-4" />
                Mark all read
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {notificationsQuery.isLoading ? (
              <div className="flex justify-center py-10"><Spinner className="h-5 w-5 text-brand-400" /></div>
            ) : notificationsQuery.isError ? (
              <ErrorState
                title="Could not load notifications"
                message={errorMessage(notificationsQuery.error)}
                onRetry={() => void notificationsQuery.refetch()}
              />
            ) : (notifications?.items.length ?? 0) === 0 ? (
              <EmptyState
                icon={Inbox}
                title={unreadOnly ? "No unread notifications" : "No notifications yet"}
                description="Notifications are created when an alert is raised for a company you belong to."
              />
            ) : (
              <div className="space-y-3">
                <ul className="divide-y divide-border rounded-md border border-border">
                  {notifications?.items.map((notification) => (
                    <li key={notification.id}>
                      <div
                        className={cn(
                          "flex items-start gap-3 px-3 py-3",
                          !notification.read_at && "bg-brand-500/[0.04]",
                        )}
                      >
                        <span
                          aria-hidden="true"
                          className={cn(
                            "mt-1.5 h-2 w-2 shrink-0 rounded-full",
                            notification.severity === "critical"
                              ? "bg-critical"
                              : notification.severity === "high"
                                ? "bg-high"
                                : "bg-info",
                          )}
                        />
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <p className="text-sm font-medium text-slate-200">{notification.title}</p>
                            <SeverityBadge severity={notification.severity} />
                            {notification.read_at ? (
                              <Badge tone="neutral">Read</Badge>
                            ) : (
                              <Badge tone="brand">Unread</Badge>
                            )}
                          </div>
                          {notification.message ? (
                            <p className="mt-0.5 text-xs text-slate-400">{notification.message}</p>
                          ) : null}
                          <p className="mt-1 text-[11px] text-slate-500">
                            {formatDateTime(notification.created_at)} · {relativeTime(notification.created_at)} · {titleize(notification.channel)}
                          </p>
                        </div>
                        {!notification.read_at ? (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => markOneMutation.mutate(notification.id)}
                            disabled={markOneMutation.isPending}
                          >
                            Mark read
                          </Button>
                        ) : null}
                      </div>
                    </li>
                  ))}
                </ul>
                <Pagination
                  page={notifications?.page ?? notificationPage}
                  total={notifications?.total}
                  pageSize={notifications?.page_size ?? 25}
                  onPageChange={setNotificationPage}
                />
              </div>
            )}
          </CardContent>
        </Card>
      ) : null}

      {tab === "preferences" ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Notification routing</CardTitle>
            </CardHeader>
            <CardContent>
              {preferencesQuery.isLoading ? (
                <div className="flex justify-center py-10"><Spinner className="h-5 w-5 text-brand-400" /></div>
              ) : preferencesQuery.isError ? (
                <ErrorState
                  title="Could not load preferences"
                  message={errorMessage(preferencesQuery.error)}
                  onRetry={() => void preferencesQuery.refetch()}
                />
              ) : (
                <div className="space-y-4">
                  <Select
                    label="Minimum severity for in-app notifications"
                    value={preferenceForm.min_severity}
                    onChange={(event) =>
                      setPreferenceForm((current) => ({
                        ...current,
                        min_severity: event.target.value,
                      }))
                    }
                    disabled={!can("alert:write")}
                  >
                    {SEVERITIES.map((value) => (
                      <option key={value} value={value}>{severityLabel(value)}</option>
                    ))}
                  </Select>

                  <div>
                    <p className="mb-2 text-xs font-medium text-slate-300">Delivery channels</p>
                    <div className="space-y-2">
                      <Checkbox
                        label="In-app notification centre"
                        description="Creates a notification for alerts at or above your minimum severity."
                        checked={preferenceForm.channels.includes("in_app")}
                        disabled={!can("alert:write")}
                        onChange={(event) =>
                          setPreferenceForm((current) => ({
                            ...current,
                            channels: event.target.checked
                              ? Array.from(new Set([...current.channels, "in_app"]))
                              : current.channels.filter((entry) => entry !== "in_app"),
                          }))
                        }
                      />
                      <Checkbox
                        label="Email, webhook and Slack delivery"
                        description="Not implemented — no outbound notification transport exists yet, so these channels are not offered."
                        checked={false}
                        disabled
                      />
                    </div>
                  </div>

                  <Checkbox
                    label="Daily digest"
                    description="Stored as a preference only — no digest scheduler or email transport is implemented."
                    checked={preferenceForm.daily_digest}
                    disabled
                  />

                  <p className="rounded-md border border-border bg-surface-raised/60 px-3 py-2 text-[11px] text-slate-500">
                    Preferences govern in-app notifications created after they are saved. Alerts themselves are always recorded in the inbox.
                  </p>

                  <Button
                    onClick={() => preferenceMutation.mutate(preferenceForm)}
                    loading={preferenceMutation.isPending}
                    disabled={!can("alert:write")}
                  >
                    Save preferences
                  </Button>
                  {!can("alert:write") ? (
                    <p className="text-[11px] text-slate-500">
                      Your role can read alerts but not change routing preferences.
                    </p>
                  ) : null}
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Muted alert types</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="mb-3 text-xs text-slate-500">
                Muted types are still recorded as alerts; only their notifications are suppressed.
              </p>
              <div className="grid gap-2 sm:grid-cols-2">
                {(enums?.alert_types ?? []).map((option) => (
                  <Checkbox
                    key={option.value}
                    label={option.label}
                    checked={preferenceForm.muted_types.includes(option.value)}
                    disabled={!can("alert:write")}
                    onChange={() => toggleMutedType(option.value)}
                  />
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      ) : null}

      <AlertDetail
        alert={selected}
        onClose={() => setSelected(null)}
        note={ackNote}
        onNoteChange={setAckNote}
        canWrite={can("alert:write")}
        acknowledging={ackMutation.isPending}
        onAcknowledge={() =>
          selected &&
          ackMutation.mutate({ id: selected.id, note: ackNote })
        }
        onDismiss={() => {
          if (!selected) return;
          setDismissTarget(selected);
          setDismissReason("");
        }}
        onResolve={() => selected && setResolveTarget(selected)}
      />

      <Modal
        open={Boolean(dismissTarget)}
        onClose={() => setDismissTarget(null)}
        title="Dismiss alert"
        description="Dismissal keeps the alert on record but removes it from the active queue."
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setDismissTarget(null)}>Cancel</Button>
            <Button
              variant="danger"
              onClick={() =>
                dismissTarget &&
                dismissMutation.mutate({
                  id: dismissTarget.id,
                  reason: dismissReason.trim(),
                })
              }
              loading={dismissMutation.isPending}
              disabled={dismissReason.trim().length < 3}
            >
              Dismiss
            </Button>
          </>
        }
      >
        <Input
          label="Reason"
          value={dismissReason}
          onChange={(event) => setDismissReason(event.target.value)}
          placeholder="e.g. Accepted business risk, covered by another control"
          maxLength={300}
          hint="At least 3 characters; stored in the audit trail."
        />
      </Modal>

      <ConfirmDialog
        open={Boolean(resolveTarget)}
        title="Resolve alert?"
        description="Resolve this alert once the underlying issue has been addressed. The alert remains in history."
        confirmLabel="Resolve"
        loading={resolveMutation.isPending}
        onConfirm={() => resolveTarget && resolveMutation.mutate(resolveTarget.id)}
        onCancel={() => setResolveTarget(null)}
      />
    </div>
  );
}

function AlertDetail({
  alert,
  onClose,
  note,
  onNoteChange,
  canWrite,
  acknowledging,
  onAcknowledge,
  onDismiss,
  onResolve,
}: {
  alert: Alert | null;
  onClose: () => void;
  note: string;
  onNoteChange: (value: string) => void;
  canWrite: boolean;
  acknowledging: boolean;
  onAcknowledge: () => void;
  onDismiss: () => void;
  onResolve: () => void;
}) {
  const isActive =
    alert?.status === "new" || alert?.status === "acknowledged";

  return (
    <Modal
      open={Boolean(alert)}
      onClose={onClose}
      title={alert?.title ?? "Alert"}
      description={
        alert
          ? `${titleize(alert.alert_type)} · ${relativeTime(alert.occurred_at)}`
          : undefined
      }
      size="lg"
      footer={
        <>
          <Button variant="ghost" size="sm" onClick={onClose}>Close</Button>
          {canWrite && isActive && alert?.status === "new" ? (
            <Button size="sm" onClick={onAcknowledge} loading={acknowledging}>
              <Check aria-hidden="true" className="h-4 w-4" />
              Acknowledge
            </Button>
          ) : null}
          {canWrite && isActive ? (
            <>
              <Button variant="ghost" size="sm" onClick={onDismiss}>
                <XCircle aria-hidden="true" className="h-4 w-4" />
                Dismiss
              </Button>
              <Button variant="ghost" size="sm" onClick={onResolve}>
                Resolve
              </Button>
            </>
          ) : null}
        </>
      }
    >
      {alert ? (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <SeverityBadge severity={alert.severity} />
            <StatusBadge status={alert.status} />
            <Badge tone="neutral">{titleize(alert.alert_type)}</Badge>
            <Badge tone="neutral">{titleize(alert.source)}</Badge>
            {alert.occurrence_count > 1 ? (
              <Badge tone="brand">{alert.occurrence_count} occurrences</Badge>
            ) : null}
          </div>

          <p className="text-sm text-slate-300">{alert.message}</p>

          {alert.recommendation ? (
            <div className="rounded-md border border-brand-500/30 bg-brand-500/[0.06] px-3 py-2">
              <p className="text-[11px] uppercase tracking-wide text-brand-400">Recommended action</p>
              <p className="mt-1 text-xs text-slate-300">{alert.recommendation}</p>
            </div>
          ) : null}

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-md bg-surface-raised/60 px-3 py-2">
              <p className="text-[11px] uppercase tracking-wide text-slate-500">First occurred</p>
              <p className="text-xs text-slate-200">{formatDateTime(alert.occurred_at)}</p>
            </div>
            <div className="rounded-md bg-surface-raised/60 px-3 py-2">
              <p className="text-[11px] uppercase tracking-wide text-slate-500">Last occurred</p>
              <p className="text-xs text-slate-200">{formatDateTime(alert.last_occurred_at ?? alert.occurred_at)}</p>
            </div>
            <div className="rounded-md bg-surface-raised/60 px-3 py-2">
              <p className="text-[11px] uppercase tracking-wide text-slate-500">Occurrences</p>
              <p className="num text-xs text-slate-200">{alert.occurrence_count}</p>
            </div>
            <div className="rounded-md bg-surface-raised/60 px-3 py-2">
              <p className="text-[11px] uppercase tracking-wide text-slate-500">Acknowledged</p>
              <p className="text-xs text-slate-200">
                {alert.acknowledged_at
                  ? `${formatDateTime(alert.acknowledged_at)}${alert.acknowledged_by_name ? ` · ${alert.acknowledged_by_name}` : ""}`
                  : "Not acknowledged"}
              </p>
            </div>
          </div>

          {alert.dismissed_reason ? (
            <div className="rounded-md border border-border px-3 py-2">
              <p className="text-[11px] uppercase tracking-wide text-slate-500">Dismiss reason</p>
              <p className="text-xs text-slate-300">{alert.dismissed_reason}</p>
            </div>
          ) : null}

          <div className="flex flex-wrap gap-3 text-xs">
            {alert.asset_id ? (
              <Link to={`/assets/${alert.asset_id}`} className="text-brand-400 hover:text-brand-300">
                Open asset {alert.asset_name ? `· ${alert.asset_name}` : ""}
              </Link>
            ) : null}
            {alert.finding_id ? (
              <Link to={`/findings?focus=${alert.finding_id}`} className="text-brand-400 hover:text-brand-300">
                Open finding
              </Link>
            ) : null}
            {alert.scan_id ? (
              <Link to={`/scans?scan=${alert.scan_id}`} className="text-brand-400 hover:text-brand-300">
                Open scan run
              </Link>
            ) : null}
          </div>

          {canWrite && alert.status === "new" ? (
            <div>
              <label htmlFor="ack-note" className="mb-1 block text-xs font-medium text-slate-300">
                Acknowledgement note (optional)
              </label>
              <textarea
                id="ack-note"
                value={note}
                onChange={(event) => onNoteChange(event.target.value)}
                rows={2}
                maxLength={500}
                placeholder="What was checked or who is handling it"
                className="w-full rounded-md border border-border bg-surface px-3 py-2 text-xs text-slate-200 placeholder:text-slate-600 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
              />
            </div>
          ) : null}

          {Object.keys(alert.payload ?? {}).length > 0 ? (
            <div>
              <p className="mb-1 text-[11px] uppercase tracking-wide text-slate-500">Event payload</p>
              <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-all rounded-md bg-surface-raised px-3 py-2 text-[11px] text-slate-400">
                {JSON.stringify(alert.payload, null, 2)}
              </pre>
            </div>
          ) : null}
        </div>
      ) : null}
    </Modal>
  );
}

export default AlertsPage;
