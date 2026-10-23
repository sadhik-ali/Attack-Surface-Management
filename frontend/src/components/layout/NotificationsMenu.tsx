import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, CheckCheck, Inbox } from "lucide-react";

import { apiRequest, errorMessage } from "@/lib/api";
import type { Notification, Page } from "@/lib/apiTypes";
import { relativeTime } from "@/lib/utils";
import { useClickOutside } from "@/hooks/useClickOutside";
import { cn } from "@/lib/utils";
import { Button, Spinner } from "@/components/ui";
import { useToast } from "@/components/ui";

const SEVERITY_DOT: Record<string, string> = {
  critical: "bg-critical",
  high: "bg-high",
  medium: "bg-medium",
  low: "bg-low",
  informational: "bg-info",
  info: "bg-info",
};

export function NotificationsMenu() {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const ref = useClickOutside<HTMLDivElement>(() => setOpen(false), open);

  const unreadQuery = useQuery({
    queryKey: ["notifications", "unread-count"],
    queryFn: () =>
      apiRequest<Page<Notification>>("/notifications", {
        params: { unread_only: true, page_size: 1 },
      }),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  const recentQuery = useQuery({
    queryKey: ["notifications", "recent"],
    queryFn: () =>
      apiRequest<Page<Notification>>("/notifications", {
        params: { page_size: 8 },
      }),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: ["notifications"] });

  const markAll = useMutation({
    mutationFn: () =>
      apiRequest<{ message: string }>("/notifications/read-all", {
        method: "POST",
      }),
    onSuccess: async (response) => {
      toast({ title: response.message, variant: "success" });
      await refresh();
    },
    onError: (error) =>
      toast({
        title: "Could not mark notifications read",
        description: errorMessage(error),
        variant: "error",
      }),
  });

  const markOne = useMutation({
    mutationFn: (id: string) =>
      apiRequest<Notification>(`/notifications/${id}/read`, {
        method: "POST",
      }),
    onSuccess: () => refresh(),
  });

  const unread = unreadQuery.data?.total ?? 0;
  const notifications = recentQuery.data?.items ?? [];

  return (
    <div ref={ref} className="relative">
      <Button
        variant="ghost"
        size="icon"
        aria-label={
          unread > 0 ? `Notifications, ${unread} unread` : "Notifications"
        }
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
        className="relative"
      >
        <Bell aria-hidden="true" className="h-4 w-4" />
        {unread > 0 ? (
          <span className="absolute -right-0.5 -top-0.5 inline-flex min-w-[1rem] items-center justify-center rounded-full bg-critical px-1 text-[10px] font-semibold leading-4 text-white">
            {unread > 99 ? "99+" : unread}
          </span>
        ) : null}
      </Button>

      {open ? (
        <div
          role="menu"
          className="absolute right-0 top-full z-50 mt-2 w-[22rem] overflow-hidden rounded-card border border-border bg-surface-raised shadow-overlay"
        >
          <div className="flex items-center justify-between border-b border-border px-3 py-2">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              Notifications
            </p>
            <button
              type="button"
              onClick={() => markAll.mutate()}
              disabled={markAll.isPending || unread === 0}
              className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] text-brand-400 transition-colors hover:bg-brand-500/10 disabled:opacity-50"
            >
              {markAll.isPending ? (
                <Spinner className="h-3 w-3" />
              ) : (
                <CheckCheck aria-hidden="true" className="h-3 w-3" />
              )}
              Mark all read
            </button>
          </div>

          <div className="max-h-96 overflow-y-auto">
            {recentQuery.isLoading ? (
              <div className="flex items-center justify-center py-8">
                <Spinner className="h-5 w-5 text-brand-400" />
              </div>
            ) : notifications.length === 0 ? (
              <div className="flex flex-col items-center gap-1.5 px-4 py-8 text-center">
                <Inbox aria-hidden="true" className="h-5 w-5 text-slate-500" />
                <p className="text-xs text-slate-400">No notifications yet</p>
              </div>
            ) : (
              <ul className="divide-y divide-border">
                {notifications.map((notification) => (
                  <li key={notification.id}>
                    <button
                      type="button"
                      onClick={() => {
                        if (!notification.read_at) markOne.mutate(notification.id);
                        setOpen(false);
                        navigate("/alerts");
                      }}
                      className={cn(
                        "flex w-full items-start gap-2.5 px-3 py-2.5 text-left transition-colors hover:bg-surface",
                        !notification.read_at && "bg-brand-500/[0.04]",
                      )}
                    >
                      <span
                        aria-hidden="true"
                        className={cn(
                          "mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full",
                          SEVERITY_DOT[notification.severity] ?? "bg-info",
                        )}
                      />
                      <span className="min-w-0 flex-1">
                        <span className="flex items-start justify-between gap-2">
                          <span className="line-clamp-1 text-xs font-medium text-slate-200">
                            {notification.title}
                          </span>
                          {!notification.read_at ? (
                            <span
                              aria-label="Unread"
                              className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-brand-400"
                            />
                          ) : null}
                        </span>
                        {notification.message ? (
                          <span className="mt-0.5 line-clamp-2 block text-[11px] text-slate-500">
                            {notification.message}
                          </span>
                        ) : null}
                        <span className="mt-1 block text-[10px] text-slate-600">
                          {relativeTime(notification.created_at)}
                        </span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="border-t border-border p-1.5">
            <Link
              to="/alerts"
              onClick={() => setOpen(false)}
              className="block rounded-md px-2.5 py-2 text-center text-xs text-slate-400 transition-colors hover:bg-surface hover:text-slate-200"
            >
              Open alert centre
            </Link>
          </div>
        </div>
      ) : null}
    </div>
  );
}
