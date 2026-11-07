// Client HTTP : jeton en mémoire de session, gestion des erreurs en français,
// téléchargement des exports.
const BASE = "/api/v1";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

let token: string | null = sessionStorage.getItem("gpc_token");
let onUnauthorized: (() => void) | null = null;

export function setToken(t: string | null) {
  token = t;
  if (t) sessionStorage.setItem("gpc_token", t);
  else sessionStorage.removeItem("gpc_token");
}
export function getToken() {
  return token;
}
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

function detail(body: any): string {
  if (!body) return "Erreur inconnue";
  if (typeof body.detail === "string") return body.detail;
  if (Array.isArray(body.detail))
    return body.detail.map((d: any) => `${(d.loc || []).slice(1).join(".")} : ${d.msg}`).join(" ; ");
  return JSON.stringify(body);
}

export async function api<T = any>(path: string, opts: { method?: string; body?: any; form?: FormData; headers?: Record<string, string> } = {}): Promise<T> {
  const headers: Record<string, string> = { ...(opts.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;
  let body: any;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  const res = await fetch(BASE + path, { method: opts.method || (body ? "POST" : "GET"), headers, body });
  if (res.status === 401 && !path.startsWith("/auth/login")) {
    onUnauthorized?.();
  }
  const ct = res.headers.get("content-type") || "";
  const data = ct.includes("application/json") ? await res.json() : null;
  if (!res.ok) throw new ApiError(res.status, detail(data));
  return data as T;
}

export async function download(path: string, fallbackName = "export") {
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(BASE + path, { method: path.includes("/accounting/export") ? "POST" : "GET", headers });
  if (!res.ok) {
    let msg = "Téléchargement impossible";
    try {
      msg = detail(await res.json());
    } catch { /* ignore */ }
    throw new ApiError(res.status, msg);
  }
  const blob = await res.blob();
  const cd = res.headers.get("content-disposition") || "";
  const m = /filename="?([^"]+)"?/.exec(cd);
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = m ? m[1] : fallbackName;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 5000);
}

export function qs(params: Record<string, any>): string {
  const p = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  });
  const s = p.toString();
  return s ? `?${s}` : "";
}
