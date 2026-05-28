const BASE = import.meta.env.VITE_API_URL || "/api/v1";

export class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, message: string, body: unknown) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

function formatDetail(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (!item || typeof item !== "object") return null;
        const obj = item as { loc?: unknown; msg?: unknown; message?: unknown };
        const msg = typeof obj.msg === "string" ? obj.msg : typeof obj.message === "string" ? obj.message : null;
        if (!msg) return null;
        const loc = Array.isArray(obj.loc)
          ? obj.loc
              .filter((part) => typeof part === "string" || typeof part === "number")
              .join(".")
          : "";
        return loc ? `${loc}: ${msg}` : msg;
      })
      .filter((msg): msg is string => !!msg);
    if (messages.length) return messages.join("; ");
  }
  if (detail && typeof detail === "object") {
    const obj = detail as { msg?: unknown; message?: unknown; error?: unknown };
    if (typeof obj.message === "string") return obj.message;
    if (typeof obj.msg === "string") return obj.msg;
    if (typeof obj.error === "string") return obj.error;
  }
  return fallback || "Request failed";
}

export function formatApiErrorMessage(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    return formatDetail((body as { detail: unknown }).detail, fallback);
  }
  if (typeof body === "string" && body.trim()) return body;
  return fallback || "Request failed";
}

type TokenAccess = {
  get: () => { access: string | null; refresh: string | null };
  set: (tokens: { access: string; refresh: string }) => void;
  clear: () => void;
};

let tokenAccess: TokenAccess | null = null;

export function configureTokenAccess(t: TokenAccess) {
  tokenAccess = t;
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
  formData?: FormData;
  signal?: AbortSignal;
  raw?: boolean;
}

export async function attemptRefresh(): Promise<boolean> {
  if (!tokenAccess) return false;
  const { refresh } = tokenAccess.get();
  if (!refresh) return false;
  const res = await fetch(`${BASE}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refresh }),
  });
  if (!res.ok) {
    tokenAccess.clear();
    return false;
  }
  const data = await res.json();
  tokenAccess.set({ access: data.access, refresh: data.refresh });
  return true;
}

async function doFetch(path: string, opts: RequestOptions, attemptedRefresh = false): Promise<Response> {
  const headers: Record<string, string> = { ...(opts.headers || {}) };
  if (!headers["Authorization"] && tokenAccess) {
    const { access } = tokenAccess.get();
    if (access) headers["Authorization"] = `Bearer ${access}`;
  }
  let body: BodyInit | undefined;
  if (opts.formData) {
    body = opts.formData;
  } else if (opts.body !== undefined) {
    headers["Content-Type"] = headers["Content-Type"] || "application/json";
    body = JSON.stringify(opts.body);
  }
  const res = await fetch(`${BASE}${path}`, {
    method: opts.method || "GET",
    headers,
    body,
    signal: opts.signal,
  });
  if (res.status === 401 && !attemptedRefresh && tokenAccess) {
    const refreshed = await attemptRefresh();
    if (refreshed) return doFetch(path, opts, true);
  }
  return res;
}

export async function api<T = unknown>(path: string, opts: RequestOptions = {}): Promise<T> {
  const res = await doFetch(path, opts);
  if (!res.ok) {
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      try {
        body = await res.text();
      } catch {
        body = null;
      }
    }
    throw new ApiError(res.status, formatApiErrorMessage(body, res.statusText), body);
  }
  if (opts.raw) {
    // @ts-expect-error: caller asked for the raw response
    return res;
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  return text ? (JSON.parse(text) as T) : (undefined as T);
}

export async function apiBlob(path: string, opts: RequestOptions = {}): Promise<Blob> {
  const res = await doFetch(path, opts);
  if (!res.ok) throw new ApiError(res.status, res.statusText, null);
  return await res.blob();
}
