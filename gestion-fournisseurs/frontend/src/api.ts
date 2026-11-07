// Client HTTP : jeton de session, messages d'erreur métier lisibles, téléchargements.
const TOKEN_KEY = "ap_token";

export function getToken(): string | null {
  try { return sessionStorage.getItem(TOKEN_KEY); } catch { return null; }
}
export function setToken(t: string | null) {
  try { t ? sessionStorage.setItem(TOKEN_KEY, t) : sessionStorage.removeItem(TOKEN_KEY); } catch { /* navigation privée */ }
}

export class ApiError extends Error {
  status: number; code?: string; data?: any;
  constructor(status: number, message: string, code?: string, data?: any) {
    super(message); this.status = status; this.code = code; this.data = data;
  }
}

let onUnauthorized: () => void = () => {};
export function setUnauthorizedHandler(f: () => void) { onUnauthorized = f; }

async function request<T>(method: string, url: string, body?: any, isForm = false): Promise<T> {
  const headers: Record<string, string> = {};
  const t = getToken();
  if (t) headers["Authorization"] = `Bearer ${t}`;
  if (body !== undefined && !isForm) headers["Content-Type"] = "application/json";
  const res = await fetch(url, { method, headers, body: isForm ? body : body !== undefined ? JSON.stringify(body) : undefined });
  if (res.status === 401 && !url.endsWith("/login")) { setToken(null); onUnauthorized(); }
  if (!res.ok) {
    let msg = `Erreur ${res.status}`; let code; let data;
    try { const j = await res.json(); msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); code = j.code; data = j.data; } catch { /* corps vide */ }
    throw new ApiError(res.status, msg, code, data);
  }
  const ct = res.headers.get("content-type") || "";
  return (ct.includes("application/json") ? res.json() : (res.blob() as any)) as T;
}

export const api = {
  get: <T = any>(u: string) => request<T>("GET", u),
  post: <T = any>(u: string, b?: any) => request<T>("POST", u, b ?? {}),
  patch: <T = any>(u: string, b: any) => request<T>("PATCH", u, b),
  put: <T = any>(u: string, b: any) => request<T>("PUT", u, b),
  upload: <T = any>(u: string, f: FormData) => request<T>("POST", u, f, true),
};

export async function download(url: string) {
  const res = await fetch(url, { headers: { Authorization: `Bearer ${getToken()}` } });
  if (!res.ok) { let m = "Téléchargement impossible"; try { m = (await res.json()).detail; } catch {} throw new ApiError(res.status, m); }
  const cd = res.headers.get("content-disposition") || "";
  const name = /filename="([^"]+)"/.exec(cd)?.[1] || "export";
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

export function qs(params: Record<string, any>): string {
  const p = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "");
  return p.length ? "?" + p.map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join("&") : "";
}
