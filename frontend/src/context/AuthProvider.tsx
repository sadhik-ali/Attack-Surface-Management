import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useQueryClient } from "@tanstack/react-query";

import {
  apiRequest,
  clearTokens,
  getAccessToken,
  storeTokens,
  type TokenPayload,
} from "@/lib/api";
import type {
  CompanyAccess,
  EnumMeta,
  MeResponse,
  RoleDefinition,
  TokenResponse,
  User,
} from "@/lib/apiTypes";

const COMPANY_KEY = "asm.selected_company";

type AuthStatus = "loading" | "authenticated" | "anonymous";

type AuthContextValue = {
  status: AuthStatus;
  user: User | null;
  permissions: string[];
  companies: CompanyAccess[];
  roles: RoleDefinition[];
  enums: EnumMeta | null;
  selectedCompanyId: string | null;
  selectedCompany: CompanyAccess | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  selectCompany: (companyId: string) => void;
  refreshMe: () => Promise<void>;
  can: (permission: string, companyId?: string) => boolean;
  companyPermissions: string[];
};

const AuthContext = createContext<AuthContextValue | null>(null);

function chooseCompany(
  companies: CompanyAccess[],
  current: string | null,
): string | null {
  if (current && companies.some((company) => company.company_id === current)) {
    return current;
  }
  return companies[0]?.company_id ?? null;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<User | null>(null);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [companies, setCompanies] = useState<CompanyAccess[]>([]);
  const [roles, setRoles] = useState<RoleDefinition[]>([]);
  const [enums, setEnums] = useState<EnumMeta | null>(null);
  const [selectedCompanyId, setSelectedCompanyId] = useState<string | null>(
    () => localStorage.getItem(COMPANY_KEY),
  );

  const applySession = useCallback(
    (payload: {
      user: User;
      permissions: string[];
      companies: CompanyAccess[];
    }) => {
      setUser(payload.user);
      setPermissions(payload.permissions);
      setCompanies(payload.companies);
      setSelectedCompanyId((current) => {
        const next = chooseCompany(payload.companies, current);
        if (next) localStorage.setItem(COMPANY_KEY, next);
        else localStorage.removeItem(COMPANY_KEY);
        return next;
      });
      setStatus("authenticated");
    },
    [],
  );

  const reset = useCallback(() => {
    clearTokens();
    setUser(null);
    setPermissions([]);
    setCompanies([]);
    setRoles([]);
    setEnums(null);
    setStatus("anonymous");
    queryClient.clear();
    localStorage.removeItem(COMPANY_KEY);
  }, [queryClient]);

  useEffect(() => {
    let cancelled = false;
    const token = getAccessToken();
    if (!token) {
      setStatus("anonymous");
      return;
    }
    apiRequest<MeResponse>("/auth/me")
      .then((response) => {
        if (cancelled) return;
        applySession(response);
      })
      .catch(() => {
        if (!cancelled) reset();
      });
    return () => {
      cancelled = true;
    };
  }, [applySession, reset]);

  useEffect(() => {
    const onRefreshed = (event: Event) => {
      const detail = (event as CustomEvent<TokenPayload & Partial<TokenResponse>>)
        .detail;
      if (detail?.user) {
        applySession({
          user: detail.user,
          permissions: detail.permissions ?? [],
          companies: detail.companies ?? [],
        });
      }
    };
    const onExpired = () => reset();
    window.addEventListener("asm:session-refreshed", onRefreshed);
    window.addEventListener("asm:session-expired", onExpired);
    return () => {
      window.removeEventListener("asm:session-refreshed", onRefreshed);
      window.removeEventListener("asm:session-expired", onExpired);
    };
  }, [applySession, reset]);

  useEffect(() => {
    if (status !== "authenticated") return;
    let cancelled = false;
    apiRequest<RoleDefinition[]>("/meta/roles")
      .then((response) => {
        if (!cancelled) setRoles(response);
      })
      .catch(() => undefined);
    apiRequest<EnumMeta>("/meta/enums")
      .then((response) => {
        if (!cancelled) setEnums(response);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [status, user?.id]);

  const login = useCallback(
    async (email: string, password: string) => {
      queryClient.clear();
      const response = await apiRequest<TokenResponse>("/auth/login", {
        method: "POST",
        body: { email, password },
        auth: false,
      });
      storeTokens(response);
      applySession(response);
    },
    [applySession, queryClient],
  );

  const logout = useCallback(async () => {
    try {
      await apiRequest("/auth/logout", { method: "POST", retryOn401: false });
    } catch {
      // The local session is cleared regardless of whether the audit call fails.
    }
    reset();
  }, [reset]);

  const selectCompany = useCallback((companyId: string) => {
    setSelectedCompanyId(companyId);
    localStorage.setItem(COMPANY_KEY, companyId);
  }, []);

  const refreshMe = useCallback(async () => {
    const response = await apiRequest<MeResponse>("/auth/me");
    applySession(response);
  }, [applySession]);

  const selectedCompany = useMemo(
    () =>
      companies.find((company) => company.company_id === selectedCompanyId) ??
      null,
    [companies, selectedCompanyId],
  );

  const rolePermissions = useMemo(() => {
    const map = new Map(roles.map((role) => [role.code, role.permissions]));
    return map;
  }, [roles]);

  const companyPermissions = useMemo(() => {
    if (!selectedCompany) return permissions;
    return (
      rolePermissions.get(selectedCompany.role_code) ?? permissions
    );
  }, [permissions, rolePermissions, selectedCompany]);

  const can = useCallback(
    (permission: string, companyId?: string) => {
      const targetId = companyId ?? selectedCompanyId;
      const company = companies.find((entry) => entry.company_id === targetId);
      if (company) {
        const perms = rolePermissions.get(company.role_code);
        if (perms) return perms.includes(permission);
      }
      return permissions.includes(permission);
    },
    [companies, permissions, rolePermissions, selectedCompanyId],
  );

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      permissions,
      companies,
      roles,
      enums,
      selectedCompanyId,
      selectedCompany,
      login,
      logout,
      selectCompany,
      refreshMe,
      can,
      companyPermissions,
    }),
    [
      status,
      user,
      permissions,
      companies,
      roles,
      enums,
      selectedCompanyId,
      selectedCompany,
      login,
      logout,
      selectCompany,
      refreshMe,
      can,
      companyPermissions,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return context;
}
