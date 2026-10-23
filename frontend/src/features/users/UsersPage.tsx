import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Building2,
  KeyRound,
  Mail,
  Pencil,
  ShieldCheck,
  UserPlus,
  UserX,
  Users,
} from "lucide-react";

import { PageHeader } from "@/components/common/PageHeader";
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
  CompanyMember,
  Page,
  User,
} from "@/lib/apiTypes";
import { titleize } from "@/lib/labels";
import { formatDateTime, relativeTime } from "@/lib/utils";
import { useAuth } from "@/context/AuthProvider";

const TABS = [
  { value: "members", label: "Company members", icon: <Users aria-hidden="true" className="h-3.5 w-3.5" /> },
  { value: "directory", label: "Platform accounts", icon: <KeyRound aria-hidden="true" className="h-3.5 w-3.5" /> },
  { value: "roles", label: "Roles & permissions", icon: <ShieldCheck aria-hidden="true" className="h-3.5 w-3.5" /> },
] as const;

type TabValue = (typeof TABS)[number]["value"];

type NewUserForm = {
  email: string;
  full_name: string;
  password: string;
  job_title: string;
  role_code: string;
  company_id: string;
};

const EMPTY_USER_FORM: NewUserForm = {
  email: "",
  full_name: "",
  password: "",
  job_title: "",
  role_code: "read_only_auditor",
  company_id: "",
};

export function UsersPage() {
  const {
    selectedCompanyId,
    selectedCompany,
    companies,
    roles,
    user,
    can,
    refreshMe,
  } = useAuth();
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const isSuperAdmin = user?.role_code === "super_admin";
  const [tab, setTab] = useState<TabValue>("members");

  const [memberModalOpen, setMemberModalOpen] = useState(false);
  const [editingMember, setEditingMember] = useState<CompanyMember | null>(null);
  const [memberEmail, setMemberEmail] = useState("");
  const [memberRole, setMemberRole] = useState<string>("security_analyst");
  const [revokeTarget, setRevokeTarget] = useState<CompanyMember | null>(null);

  const [memberSearch, setMemberSearch] = useState("");

  const [directorySearch, setDirectorySearch] = useState("");
  const [directoryRole, setDirectoryRole] = useState("");
  const [directoryActive, setDirectoryActive] = useState("");
  const [directoryPage, setDirectoryPage] = useState(1);
  const [directoryPageSize] = useState(20);

  const [userModalOpen, setUserModalOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [userForm, setUserForm] = useState<NewUserForm>(EMPTY_USER_FORM);
  const [userActive, setUserActive] = useState(true);
  const [disableTarget, setDisableTarget] = useState<User | null>(null);

  const membersQuery = useQuery({
    queryKey: ["company-members", selectedCompanyId],
    queryFn: () =>
      apiRequest<CompanyMember[]>(
        `/companies/${selectedCompanyId}/members`,
      ),
    enabled: Boolean(selectedCompanyId) && tab === "members" && can("user:read"),
  });

  const directoryQuery = useQuery({
    queryKey: [
      "platform-users",
      directorySearch,
      directoryRole,
      directoryActive,
      directoryPage,
      directoryPageSize,
    ],
    queryFn: () =>
      apiRequest<Page<User>>("/users", {
        params: {
          q: directorySearch.trim() || undefined,
          role_code: directoryRole || undefined,
          is_active:
            directoryActive === "" ? undefined : directoryActive === "true",
          page: directoryPage,
          page_size: directoryPageSize,
          sort: "created_at",
          order: "desc",
        },
      }),
    enabled: tab === "directory" && isSuperAdmin,
    placeholderData: (previous) => previous,
  });

  const refreshMembers = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["company-members", selectedCompanyId] }),
      queryClient.invalidateQueries({ queryKey: ["platform-users"] }),
      refreshMe(),
    ]);
  };

  const saveMemberMutation = useMutation({
    mutationFn: (payload: { email?: string; user_id?: string; role_code: string }) =>
      apiRequest<{ id: string; message: string }>(
        `/companies/${selectedCompanyId}/members`,
        { method: "POST", body: payload },
      ),
    onSuccess: async () => {
      toast({ title: editingMember ? "Member role updated" : "Member added", variant: "success" });
      setMemberModalOpen(false);
      setEditingMember(null);
      setMemberEmail("");
      await refreshMembers();
    },
    onError: (error) =>
      toast({
        title: "Could not save membership",
        description: errorMessage(error),
        variant: "error",
      }),
  });

  const revokeMutation = useMutation({
    mutationFn: (membershipId: string) =>
      apiRequest<{ message: string }>(
        `/companies/${selectedCompanyId}/members/${membershipId}`,
        { method: "DELETE" },
      ),
    onSuccess: async (response) => {
      toast({ title: response.message, variant: "success" });
      setRevokeTarget(null);
      await refreshMembers();
    },
    onError: (error) =>
      toast({
        title: "Could not revoke access",
        description: errorMessage(error),
        variant: "error",
      }),
  });

  const createUserMutation = useMutation({
    mutationFn: (payload: NewUserForm) =>
      apiRequest<User>("/users", {
        method: "POST",
        body: {
          email: payload.email.trim(),
          full_name: payload.full_name.trim(),
          password: payload.password,
          job_title: payload.job_title.trim() || null,
          role_code: payload.role_code,
          company_id: payload.role_code === "super_admin" ? null : payload.company_id || null,
        },
      }),
    onSuccess: async (created) => {
      toast({
        title: "Account created",
        description: `${created.email} must change the temporary password at first sign-in.`,
        variant: "success",
      });
      setUserModalOpen(false);
      setUserForm(EMPTY_USER_FORM);
      await queryClient.invalidateQueries({ queryKey: ["platform-users"] });
    },
    onError: (error) =>
      toast({
        title: "Could not create account",
        description: errorMessage(error),
        variant: "error",
      }),
  });

  const updateUserMutation = useMutation({
    mutationFn: ({
      userId,
      payload,
    }: {
      userId: string;
      payload: Record<string, unknown>;
    }) =>
      apiRequest<User>(`/users/${userId}`, { method: "PATCH", body: payload }),
    onSuccess: async (updated) => {
      toast({ title: "Account updated", description: updated.email, variant: "success" });
      setUserModalOpen(false);
      setEditingUser(null);
      setDisableTarget(null);
      await queryClient.invalidateQueries({ queryKey: ["platform-users"] });
      if (updated.id === user?.id) await refreshMe();
    },
    onError: (error) =>
      toast({
        title: "Could not update account",
        description: errorMessage(error),
        variant: "error",
      }),
  });

  if (!selectedCompanyId) return null;

  const members = (membersQuery.data ?? []).filter((member) => {
    const query = memberSearch.trim().toLowerCase();
    if (!query) return true;
    return (
      member.email.toLowerCase().includes(query) ||
      member.full_name.toLowerCase().includes(query)
    );
  });

  const roleOptions = roles.length
    ? roles
    : [
        { code: "company_admin", name: "Company Admin" },
        { code: "security_analyst", name: "Security Analyst" },
        { code: "read_only_auditor", name: "Read-Only Auditor" },
      ];

  const openAddMember = () => {
    setEditingMember(null);
    setMemberEmail("");
    setMemberRole("security_analyst");
    setMemberModalOpen(true);
  };

  const openEditMember = (member: CompanyMember) => {
    setEditingMember(member);
    setMemberEmail(member.email);
    setMemberRole(member.role_code);
    setMemberModalOpen(true);
  };

  const submitMember = () => {
    if (!editingMember && !memberEmail.trim()) {
      toast({ title: "Enter the account email", variant: "error" });
      return;
    }
    saveMemberMutation.mutate(
      editingMember
        ? { user_id: editingMember.user_id, role_code: memberRole }
        : { email: memberEmail.trim().toLowerCase(), role_code: memberRole },
    );
  };

  const openCreateUser = () => {
    setEditingUser(null);
    setUserForm({
      ...EMPTY_USER_FORM,
      company_id: selectedCompanyId,
    });
    setUserActive(true);
    setUserModalOpen(true);
  };

  const openEditUser = (target: User) => {
    setEditingUser(target);
    setUserForm({
      email: target.email,
      full_name: target.full_name,
      password: "",
      job_title: target.job_title ?? "",
      role_code: target.role_code,
      company_id: target.memberships[0]?.company_id ?? "",
    });
    setUserActive(target.is_active);
    setUserModalOpen(true);
  };

  const submitUser = () => {
    if (!userForm.full_name.trim()) {
      toast({ title: "Full name is required", variant: "error" });
      return;
    }
    if (editingUser) {
      updateUserMutation.mutate({
        userId: editingUser.id,
        payload: {
          full_name: userForm.full_name.trim(),
          job_title: userForm.job_title.trim() || null,
          role_code: userForm.role_code,
          is_active: userActive,
        },
      });
      return;
    }

    if (!userForm.email.trim()) {
      toast({ title: "Email is required", variant: "error" });
      return;
    }
    if (
      userForm.password.length < 12 ||
      !/[A-Z]/.test(userForm.password) ||
      !/[a-z]/.test(userForm.password) ||
      !/[0-9]/.test(userForm.password)
    ) {
      toast({
        title: "Password is not strong enough",
        description: "Use at least 12 characters with an uppercase letter, a lowercase letter and a digit.",
        variant: "error",
      });
      return;
    }
    if (userForm.role_code !== "super_admin" && !userForm.company_id) {
      toast({ title: "Choose a company for this tenant-scoped role", variant: "error" });
      return;
    }
    createUserMutation.mutate(userForm);
  };

  const canReadMembers = can("user:read");
  const canWriteMembers = can("user:write");

  const visibleTabs = TABS.filter((item) => item.value !== "directory" || isSuperAdmin);

  return (
    <div>
      <PageHeader
        title="Users & roles"
        description="Company membership controls access to this tenant. Platform accounts are created by a Super Admin; company administrators grant or revoke access and choose a role."
        actions={
          canWriteMembers ? (
            <Button size="sm" onClick={openAddMember}>
              <UserPlus aria-hidden="true" className="h-4 w-4" />
              Add member
            </Button>
          ) : null
        }
      />

      <Tabs
        value={tab}
        onValueChange={(value) => setTab(value as TabValue)}
        items={visibleTabs.map((item) => ({
          value: item.value,
          label: item.label,
          icon: item.icon,
          content: null,
        }))}
        className="mb-4"
      />

      {tab === "members" ? (
        !canReadMembers ? (
          <Card>
            <CardContent>
              <EmptyState
                icon={ShieldCheck}
                title="Membership view requires user:read"
                description="Your role does not include access to the user directory."
              />
            </CardContent>
          </Card>
        ) : (
          <Card>
            <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
              <CardTitle>{selectedCompany?.name ?? "Company"} members</CardTitle>
              <SearchInput
                value={memberSearch}
                onChange={setMemberSearch}
                placeholder="Search members"
                className="sm:max-w-xs"
              />
            </CardHeader>
            <CardContent>
              {membersQuery.isLoading ? (
                <TableLoading columns={6} rows={5} />
              ) : membersQuery.isError ? (
                <ErrorState
                  title="Could not load members"
                  message={errorMessage(membersQuery.error)}
                  onRetry={() => void membersQuery.refetch()}
                />
              ) : members.length === 0 ? (
                <EmptyState
                  icon={Users}
                  title={memberSearch ? "No members match the search" : "No members yet"}
                  description={
                    memberSearch
                      ? "Clear the search to see the whole membership."
                      : "Add an existing platform account to this company and choose its role."
                  }
                  action={
                    canWriteMembers && !memberSearch ? (
                      <Button size="sm" onClick={openAddMember}>Add member</Button>
                    ) : null
                  }
                />
              ) : (
                <div className="overflow-x-auto rounded-md border border-border">
                  <Table>
                    <THead>
                      <Tr>
                        <Th>Member</Th>
                        <Th>Role</Th>
                        <Th>Status</Th>
                        <Th className="hidden lg:table-cell">Last sign-in</Th>
                        <Th className="hidden xl:table-cell">Access expires</Th>
                        <Th>Actions</Th>
                      </Tr>
                    </THead>
                    <TBody>
                      {members.map((member) => (
                        <Tr key={member.id}>
                          <Td>
                            <div className="flex items-center gap-2">
                              <span
                                aria-hidden="true"
                                className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold text-white"
                                style={{ backgroundColor: member.avatar_color ?? "#334155" }}
                              >
                                {member.full_name.slice(0, 1).toUpperCase()}
                              </span>
                              <div className="min-w-0">
                                <p className="truncate text-xs font-medium text-slate-200">{member.full_name}</p>
                                <p className="truncate text-[11px] text-slate-500">{member.email}</p>
                              </div>
                            </div>
                          </Td>
                          <Td><Badge tone="brand">{member.role_name ?? titleize(member.role_code)}</Badge></Td>
                          <Td>
                            {member.is_active ? <Badge tone="low" dot>Active</Badge> : <Badge tone="neutral" dot>Revoked</Badge>}
                          </Td>
                          <Td className="hidden lg:table-cell">
                            <span className="text-xs text-slate-400">
                              {member.last_login_at ? relativeTime(member.last_login_at) : "Never"}
                            </span>
                          </Td>
                          <Td className="hidden xl:table-cell">
                            <span className="text-xs text-slate-400">
                              {member.expires_at ? formatDateTime(member.expires_at) : "No expiry"}
                            </span>
                          </Td>
                          <Td>
                            {canWriteMembers && member.is_active ? (
                              <div className="flex gap-1">
                                <Button variant="ghost" size="sm" onClick={() => openEditMember(member)}>
                                  <Pencil aria-hidden="true" className="h-3.5 w-3.5" />
                                  Role
                                </Button>
                                <Button variant="ghost" size="sm" onClick={() => setRevokeTarget(member)}>
                                  <UserX aria-hidden="true" className="h-3.5 w-3.5" />
                                  Revoke
                                </Button>
                              </div>
                            ) : (
                              <span className="text-[11px] text-slate-500">—</span>
                            )}
                          </Td>
                        </Tr>
                      ))}
                    </TBody>
                  </Table>
                </div>
              )}
              <p className="mt-3 text-[11px] text-slate-500">
                Membership roles apply per company. A user can hold different roles in different companies; the selected company in the header determines the permissions in effect.
              </p>
            </CardContent>
          </Card>
        )
      ) : null}

      {tab === "directory" && isSuperAdmin ? (
        <Card>
          <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3">
            <CardTitle>Platform accounts</CardTitle>
            <Button size="sm" onClick={openCreateUser}>
              <UserPlus aria-hidden="true" className="h-4 w-4" />
              Create account
            </Button>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <SearchInput
                value={directorySearch}
                onChange={(value) => {
                  setDirectorySearch(value);
                  setDirectoryPage(1);
                }}
                placeholder="Search name or email"
              />
              <Select
                aria-label="Role"
                value={directoryRole}
                onChange={(event) => {
                  setDirectoryRole(event.target.value);
                  setDirectoryPage(1);
                }}
                className="w-48"
              >
                <option value="">All roles</option>
                {roles.map((role) => (
                  <option key={role.code} value={role.code}>{role.name}</option>
                ))}
              </Select>
              <Select
                aria-label="Account status"
                value={directoryActive}
                onChange={(event) => {
                  setDirectoryActive(event.target.value);
                  setDirectoryPage(1);
                }}
                className="w-40"
              >
                <option value="">Any status</option>
                <option value="true">Active</option>
                <option value="false">Disabled</option>
              </Select>
            </div>

            {directoryQuery.isLoading ? (
              <TableLoading columns={6} />
            ) : directoryQuery.isError ? (
              <ErrorState
                title="Could not load accounts"
                message={errorMessage(directoryQuery.error)}
                onRetry={() => void directoryQuery.refetch()}
              />
            ) : (directoryQuery.data?.items.length ?? 0) === 0 ? (
              <EmptyState
                icon={Users}
                title="No accounts match these filters"
                description="Adjust the search or create a new platform account."
              />
            ) : (
              <>
                <div className="overflow-x-auto rounded-md border border-border">
                  <Table>
                    <THead>
                      <Tr>
                        <Th>Account</Th>
                        <Th>Platform role</Th>
                        <Th>Memberships</Th>
                        <Th>Status</Th>
                        <Th className="hidden lg:table-cell">Last sign-in</Th>
                        <Th>Actions</Th>
                      </Tr>
                    </THead>
                    <TBody>
                      {directoryQuery.data?.items.map((account) => (
                        <Tr key={account.id}>
                          <Td>
                            <p className="text-xs font-medium text-slate-200">{account.full_name}</p>
                            <p className="text-[11px] text-slate-500">{account.email}</p>
                            {account.job_title ? <p className="text-[11px] text-slate-600">{account.job_title}</p> : null}
                          </Td>
                          <Td>
                            <Badge tone={account.role_code === "super_admin" ? "medium" : "brand"}>
                              {account.role_name ?? titleize(account.role_code)}
                            </Badge>
                          </Td>
                          <Td>
                            <div className="flex flex-wrap gap-1">
                              {account.memberships.length === 0 ? (
                                <span className="text-[11px] text-slate-500">Platform only</span>
                              ) : (
                                account.memberships.map((membership) => (
                                  <Badge key={membership.company_id} tone="neutral">
                                    {membership.company_name ?? membership.company_id}
                                  </Badge>
                                ))
                              )}
                            </div>
                          </Td>
                          <Td>
                            {account.is_active ? <Badge tone="low" dot>Active</Badge> : <Badge tone="critical" dot>Disabled</Badge>}
                            {account.must_change_password ? (
                              <p className="mt-1 text-[10px] text-slate-500">Must change password</p>
                            ) : null}
                          </Td>
                          <Td className="hidden lg:table-cell">
                            <span className="text-xs text-slate-400">
                              {account.last_login_at ? relativeTime(account.last_login_at) : "Never"}
                            </span>
                          </Td>
                          <Td>
                            <div className="flex gap-1">
                              <Button variant="ghost" size="sm" onClick={() => openEditUser(account)}>
                                <Pencil aria-hidden="true" className="h-3.5 w-3.5" />
                                Edit
                              </Button>
                              {account.is_active && account.id !== user?.id ? (
                                <Button variant="ghost" size="sm" onClick={() => setDisableTarget(account)}>
                                  <UserX aria-hidden="true" className="h-3.5 w-3.5" />
                                  Disable
                                </Button>
                              ) : null}
                            </div>
                          </Td>
                        </Tr>
                      ))}
                    </TBody>
                  </Table>
                </div>
                <Pagination
                  page={directoryQuery.data?.page ?? directoryPage}
                  total={directoryQuery.data?.total}
                  pageSize={directoryQuery.data?.page_size ?? directoryPageSize}
                  onPageChange={setDirectoryPage}
                />
              </>
            )}
            <p className="text-[11px] text-slate-500">
              Creating an account sends no email. The temporary password must be shared out of band; the user is prompted to change it at first sign-in.
            </p>
          </CardContent>
        </Card>
      ) : null}

      {tab === "roles" ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {roles.map((role) => (
            <Card key={role.code}>
              <CardHeader className="flex flex-row items-start justify-between gap-2">
                <div>
                  <CardTitle>{role.name}</CardTitle>
                  <p className="mt-1 text-xs text-slate-500">{role.description}</p>
                </div>
                <Badge tone={role.tenant_scoped ? "brand" : "medium"}>
                  {role.tenant_scoped ? "Company scoped" : "Platform scoped"}
                </Badge>
              </CardHeader>
              <CardContent>
                <p className="mb-2 text-[11px] uppercase tracking-wide text-slate-500">
                  {role.permissions.length} permissions
                </p>
                <div className="flex flex-wrap gap-1">
                  {role.permissions
                    .slice()
                    .sort()
                    .map((permission) => (
                      <Badge key={permission} tone="neutral">
                        {titleize(permission.replace(":", " "))}
                      </Badge>
                    ))}
                </div>
                {role.tenant_scoped ? (
                  <p className="mt-3 text-[11px] text-slate-500">
                    Effective only inside companies where the user holds this membership; tenancy is enforced in addition to permissions.
                  </p>
                ) : null}
              </CardContent>
            </Card>
          ))}
          <Card className="lg:col-span-2">
            <CardContent className="flex gap-2 text-xs text-slate-400">
              <Building2 aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0 text-brand-400" />
              Role definitions are served by the backend (<span className="num text-slate-300">/meta/roles</span>), so the UI never holds a second copy of the permission matrix.
            </CardContent>
          </Card>
        </div>
      ) : null}

      <Modal
        open={memberModalOpen}
        onClose={() => setMemberModalOpen(false)}
        title={editingMember ? "Change membership role" : "Add company member"}
        description={
          editingMember
            ? `${editingMember.full_name} · ${editingMember.email}`
            : "The account must already exist on the platform."
        }
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setMemberModalOpen(false)}>Cancel</Button>
            <Button onClick={submitMember} loading={saveMemberMutation.isPending}>
              {editingMember ? "Update role" : "Add member"}
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <Input
            label="Account email"
            type="email"
            value={memberEmail}
            onChange={(event) => setMemberEmail(event.target.value)}
            disabled={Boolean(editingMember)}
            placeholder="analyst@company.example"
            leftAddon={<Mail aria-hidden="true" className="h-3.5 w-3.5" />}
            hint={editingMember ? "The account cannot be changed here." : "If no account exists, a Super Admin must create it first."}
          />
          <Select
            label="Company role"
            value={memberRole}
            onChange={(event) => setMemberRole(event.target.value)}
          >
            {roleOptions
              .filter((role) => role.code !== "super_admin")
              .map((role) => (
                <option key={role.code} value={role.code}>{role.name}</option>
              ))}
          </Select>
          <p className="text-[11px] text-slate-500">
            Super Admin is a platform role and cannot be granted through company membership.
          </p>
        </div>
      </Modal>

      <ConfirmDialog
        open={Boolean(revokeTarget)}
        title="Revoke company access?"
        description={
          revokeTarget
            ? `${revokeTarget.full_name} will lose access to ${selectedCompany?.name ?? "this company"}. Their account and other memberships are unaffected.`
            : undefined
        }
        confirmLabel="Revoke access"
        destructive
        loading={revokeMutation.isPending}
        onConfirm={() => revokeTarget && revokeMutation.mutate(revokeTarget.id)}
        onCancel={() => setRevokeTarget(null)}
      />

      <Modal
        open={userModalOpen}
        onClose={() => setUserModalOpen(false)}
        title={editingUser ? "Edit platform account" : "Create platform account"}
        description={
          editingUser
            ? editingUser.email
            : "Accounts are created by a Super Admin; company membership can be granted at the same time."
        }
        size="md"
        footer={
          <>
            <Button variant="ghost" onClick={() => setUserModalOpen(false)}>Cancel</Button>
            <Button
              onClick={submitUser}
              loading={createUserMutation.isPending || updateUserMutation.isPending}
            >
              {editingUser ? "Save changes" : "Create account"}
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <Input
              label="Full name"
              value={userForm.full_name}
              onChange={(event) => setUserForm((current) => ({ ...current, full_name: event.target.value }))}
              maxLength={200}
            />
            <Input
              label="Job title"
              value={userForm.job_title}
              onChange={(event) => setUserForm((current) => ({ ...current, job_title: event.target.value }))}
              maxLength={150}
            />
          </div>
          <Input
            label="Email"
            type="email"
            value={userForm.email}
            onChange={(event) => setUserForm((current) => ({ ...current, email: event.target.value }))}
            disabled={Boolean(editingUser)}
          />
          {!editingUser ? (
            <Input
              label="Temporary password"
              type="password"
              value={userForm.password}
              onChange={(event) => setUserForm((current) => ({ ...current, password: event.target.value }))}
              hint="At least 12 characters with an uppercase letter, a lowercase letter and a digit. No email is sent."
            />
          ) : null}
          <Select
            label="Platform role"
            value={userForm.role_code}
            onChange={(event) => setUserForm((current) => ({ ...current, role_code: event.target.value }))}
          >
            {roles.map((role) => (
              <option key={role.code} value={role.code}>{role.name}</option>
            ))}
          </Select>
          {!editingUser && userForm.role_code !== "super_admin" ? (
            <Select
              label="Initial company membership"
              value={userForm.company_id}
              onChange={(event) => setUserForm((current) => ({ ...current, company_id: event.target.value }))}
            >
              <option value="">Choose a company</option>
              {companies.map((company) => (
                <option key={company.company_id} value={company.company_id}>{company.name}</option>
              ))}
            </Select>
          ) : null}
          {editingUser ? (
            <Checkbox
              label="Account active"
              description="Disabled accounts cannot sign in. The last active Super Admin cannot be disabled."
              checked={userActive}
              onChange={(event) => setUserActive(event.target.checked)}
            />
          ) : null}
          <p className="text-[11px] text-slate-500">
            Changing the platform role here does not rewrite existing per-company membership roles.
          </p>
        </div>
      </Modal>

      <ConfirmDialog
        open={Boolean(disableTarget)}
        title="Disable this account?"
        description={
          disableTarget
            ? `${disableTarget.email} will be signed out of new sessions. Existing company memberships remain on record.`
            : undefined
        }
        confirmLabel="Disable account"
        destructive
        loading={updateUserMutation.isPending}
        onConfirm={() =>
          disableTarget &&
          updateUserMutation.mutate({
            userId: disableTarget.id,
            payload: { is_active: false },
          })
        }
        onCancel={() => setDisableTarget(null)}
      />
    </div>
  );
}

export default UsersPage;
