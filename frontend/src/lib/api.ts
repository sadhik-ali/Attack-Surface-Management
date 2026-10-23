export type ApiErrorBody = {
  code: string;
  message: string;
  details?: unknown;
  request_id?: string;
};

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details?: unknown;
  readonly requestId?: string;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message || `Request failed (${status})`);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code || "request_failed";
    this.details = body.details;
    this.requestId = body.request_id;
  }
}

const API_BASE = "/api/v1";
const ACCESS_KEY = "asm.access_token";
const REFRESH_KEY = "asm.refresh_token";
const EXPIRES_KEY = "asm.access_expires_at";

export type TokenPayload = {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  token_type: string;
};

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_KEY);
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY);
}

export function storeTokens(payload: TokenPayload): void {
  localStorage.setItem(ACCESS_KEY, payload.access_token);
  localStorage.setItem(REFRESH_KEY, payload.refresh_token);
  localStorage.setItem(
    EXPIRES_KEY,
    String(Date.now() + payload.expires_in * 1000),
  );
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
  localStorage.removeItem(EXPIRES_KEY);
}

function notifyExpired(): void {
  window.dispatchEvent(new CustomEvent("asm:session-expired"));
}

let refreshInFlight: Promise<boolean> | null = null;

async function refreshSession(): Promise<boolean> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return false;
  try {
    const response = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!response.ok) return false;
    const payload = (await response.json()) as TokenPayload & {
      user?: unknown;
      permissions?: unknown;
      companies?: unknown;
    };
    storeTokens(payload);
    window.dispatchEvent(
      new CustomEvent("asm:session-refreshed", { detail: payload }),
    );
    return true;
  } catch {
    return false;
  }
}

export async function ensureFreshSession(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = refreshSession().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

export type QueryValue =
  | string
  | number
  | boolean
  | null
  | undefined
  | (string | number)[];

export function buildQuery(
  params?: Record<string, QueryValue>,
): string {
  if (!params) return "";
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) {
      for (const entry of value) {
        if (entry !== undefined && entry !== null && entry !== "") {
          search.append(key, String(entry));
        }
      }
    } else {
      search.append(key, String(value));
    }
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}

type RequestOptions = {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  params?: Record<string, QueryValue>;
  signal?: AbortSignal;
  auth?: boolean;
  retryOn401?: boolean;
  rawBody?: BodyInit;
};

async function parseError(response: Response): Promise<ApiError> {
  let body: ApiErrorBody = {
    code: `http_${response.status}`,
    message: response.statusText || "Request failed",
  };
  try {
    const data = (await response.json()) as
      | { error?: ApiErrorBody; detail?: unknown }
      | ApiErrorBody;
    if (data && typeof data === "object" && "error" in data && data.error) {
      body = data.error;
    } else if (data && typeof data === "object" && "detail" in data) {
      body = {
        code: `http_${response.status}`,
        message:
          typeof data.detail === "string"
            ? data.detail
            : "Request validation failed",
        details: data.detail,
      };
    } else if (data && typeof data === "object" && "message" in data) {
      body = data as ApiErrorBody;
    }
  } catch {
    // Non-JSON error bodies keep the status text.
  }
  return new ApiError(response.status, body);
}

export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const {
    method = "GET",
    body,
    params,
    signal,
    auth = true,
    retryOn401 = true,
    rawBody,
  } = options;

  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth) {
    const token = getAccessToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}${buildQuery(params)}`, {
      method,
      headers,
      body: rawBody ?? (body !== undefined ? JSON.stringify(body) : undefined),
      signal,
    });
  } catch (error) {
    if ((error as Error).name === "AbortError") throw error;
    throw new ApiError(0, {
      code: "network_error",
      message:
        "The API could not be reached. Check that the backend is running and try again.",
    });
  }

  if (
    response.status === 401 &&
    auth &&
    retryOn401 &&
    getRefreshToken() &&
    !path.startsWith("/auth/login")
  ) {
    const refreshed = await ensureFreshSession();
    if (refreshed) {
      return apiRequest<T>(path, { ...options, retryOn401: false });
    }
    clearTokens();
    notifyExpired();
  }

  if (!response.ok) {
    throw await parseError(response);
  }

  if (response.status === 204) return undefined as T;
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    return (await response.json()) as T;
  }
  return (await response.text()) as T;
}

async function requestFile(
  path: string,
  init: { method?: "GET" | "POST"; params?: Record<string, QueryValue>; body?: unknown },
  retry = true,
): Promise<{ blob: Blob; filename: string | null }> {
  const headers: Record<string, string> = {};
  const token = getAccessToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (init.body !== undefined) headers["Content-Type"] = "application/json";
  const response = await fetch(
    `${API_BASE}${path}${buildQuery(init.params)}`,
    {
      method: init.method ?? "GET",
      headers,
      body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
    },
  );
  if (response.status === 401 && retry) {
    const refreshed = await ensureFreshSession();
    if (refreshed) return requestFile(path, init, false);
  }
  if (!response.ok) throw await parseError(response);
  const disposition = response.headers.get("content-disposition") ?? "";
  const match = /filename="?([^";]+)"?/i.exec(disposition);
  return { blob: await response.blob(), filename: match?.[1] ?? null };
}

export async function downloadFile(
  path: string,
  params?: Record<string, QueryValue>,
): Promise<{ blob: Blob; filename: string | null }> {
  return requestFile(path, { params });
}

export async function downloadPost(
  path: string,
  body: unknown,
): Promise<{ blob: Blob; filename: string | null }> {
  return requestFile(path, { method: "POST", body });
}

export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Something went wrong";
}
