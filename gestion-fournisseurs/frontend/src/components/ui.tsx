import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, download } from "../api";
import { t } from "../i18n";
import { dt, money } from "../format";

// ---------------------------------------------------------------- session
export type Me = { id: number; email: string; full_name: string; role: string; role_label: string; permissions: string[]; company: any };
export const MeContext = createContext<Me | null>(null);
export const useMe = () => useContext(MeContext)!;
export const useCan = () => { const me = useMe(); return (p: string) => me.permissions.includes(p); };

// ---------------------------------------------------------------- notifications
type Toast = { id: number; kind: "ok" | "err" | "warn"; text: string };
const ToastCtx = createContext<(kind: Toast["kind"], text: string) => void>(() => {});
export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const push = useCallback((kind: Toast["kind"], text: string) => {
    const id = Date.now() + Math.random();
    setItems((x) => [...x, { id, kind, text }]);
    setTimeout(() => setItems((x) => x.filter((i) => i.id !== id)), kind === "err" ? 9000 : 5000);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts" role="status">
        {items.map((i) => <div key={i.id} className={`toast ${i.kind}`} onClick={() => setItems((x) => x.filter((y) => y.id !== i.id))}>{i.text}</div>)}
      </div>
    </ToastCtx.Provider>
  );
}
export const useToast = () => useContext(ToastCtx);

/** Exécute une action serveur avec message de succès / d'erreur métier. */
export function useAction() {
  const toast = useToast();
  return async <T,>(f: () => Promise<T>, ok?: string): Promise<T | undefined> => {
    try {
      const r = await f();
      if (ok) toast("ok", ok);
      const w = (r as any)?.avertissements;
      if (Array.isArray(w)) w.forEach((x: string) => toast("warn", x));
      return r;
    } catch (e) {
      toast("err", e instanceof ApiError ? e.message : String(e));
      return undefined;
    }
  };
}

// ---------------------------------------------------------------- chargement
export function useLoad<T>(f: () => Promise<T>, deps: any[] = []): [T | undefined, () => void, boolean, string | undefined] {
  const [data, setData] = useState<T>();
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string>();
  const [n, setN] = useState(0);
  useEffect(() => {
    let alive = true;
    setLoading(true);
    f().then((d) => { if (alive) { setData(d); setErr(undefined); } })
      .catch((e) => alive && setErr(e instanceof ApiError ? e.message : String(e)))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, n]);
  return [data, () => setN((x) => x + 1), loading, err];
}

export function Loading({ err }: { err?: string }) {
  return err ? <div className="alert err">{err}</div> : <div className="muted pad">Chargement…</div>;
}

// ---------------------------------------------------------------- éléments
const TONE: Record<string, string> = {
  reglee: "ok", validee: "ok", conforme: "ok", actif: "ok", verifie: "ok", debite: "ok", approuvee: "ok", approuve: "ok",
  recue: "ok", resolu: "ok", clos: "muted", faible: "ok",
  echue: "err", en_litige: "err", bloquant: "err", bloque: "err", rejete: "err", rejetee: "err", critique: "err", a_risque: "err",
  annulee: "muted", annule: "muted", remplace: "muted", cloturee: "muted", brouillon: "muted", inactif: "muted",
  en_attente_validation: "warn", a_approuver: "warn", partiellement_reglee: "warn", a_verifier: "warn", en_attente: "warn",
  ecarts: "warn", ouvert: "warn", en_cours: "warn", partiellement_recue: "warn", modere: "warn", eleve: "err", emis: "info",
  non_echue: "info", soumise: "info", proposee: "info", strategique: "info",
};
export function Badge({ v }: { v?: string | null }) {
  if (!v) return null;
  return <span className={`badge ${TONE[v] || "info"}`}>{t(v)}</span>;
}

export function Card({ title, children, actions, className }: { title?: React.ReactNode; children: React.ReactNode; actions?: React.ReactNode; className?: string }) {
  return (
    <section className={`card ${className || ""}`}>
      {(title || actions) && <header className="card-h"><h3>{title}</h3><div className="row gap">{actions}</div></header>}
      {children}
    </section>
  );
}

export function Kpi({ label, value, hint, tone }: { label: string; value: React.ReactNode; hint?: string; tone?: string }) {
  return <div className={`kpi ${tone || ""}`}><div className="kpi-l">{label}</div><div className="kpi-v">{value}</div>{hint && <div className="kpi-h">{hint}</div>}</div>;
}

export function Modal({ title, onClose, children, wide }: { title: string; onClose: () => void; children: React.ReactNode; wide?: boolean }) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  return (
    <div className="modal-bg" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`modal ${wide ? "wide" : ""}`} role="dialog" aria-label={title}>
        <header className="card-h"><h3>{title}</h3><button className="btn ghost" onClick={onClose} aria-label="Fermer">✕</button></header>
        {children}
      </div>
    </div>
  );
}

export function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return <label className="field"><span>{label}</span>{children}{hint && <small className="muted">{hint}</small>}</label>;
}

export function Tabs({ tabs, active, onChange }: { tabs: [string, string][]; active: string; onChange: (k: string) => void }) {
  return <div className="tabs">{tabs.map(([k, l]) => <button key={k} className={k === active ? "on" : ""} onClick={() => onChange(k)}>{l}</button>)}</div>;
}

export function ExportButtons({ name, params = "" }: { name: string; params?: string }) {
  const act = useAction();
  const go = (f: string) => act(() => download(`/api/reports/export/${name}?format=${f}${params}`));
  return <div className="row gap"><button className="btn sm" onClick={() => go("xlsx")}>Excel</button><button className="btn sm" onClick={() => go("pdf")}>PDF</button><button className="btn sm" onClick={() => go("csv")}>CSV</button></div>;
}

// ---------------------------------------------------------------- tableau générique
export type Col<T> = {
  key: string; label: string; kind?: "money" | "date" | "badge" | "num"; cur?: (r: T) => string | undefined;
  render?: (r: T) => React.ReactNode; link?: (r: T) => string; align?: "right"; total?: boolean;
};

export function DataTable<T extends Record<string, any>>({ rows, cols, empty = "Aucune donnée.", filter = true, onRow, selectable, selected, onSelect }:
  { rows: T[]; cols: Col<T>[]; empty?: string; filter?: boolean; onRow?: (r: T) => void;
    selectable?: (r: T) => boolean; selected?: Set<any>; onSelect?: (s: Set<any>) => void }) {
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<{ k: string; d: 1 | -1 } | null>(null);
  const view = useMemo(() => {
    let r = rows;
    if (q) {
      const s = q.toLowerCase();
      r = r.filter((x) => cols.some((c) => String(x[c.key] ?? "").toLowerCase().includes(s) || t(String(x[c.key] ?? "")).toLowerCase().includes(s)));
    }
    if (sort) r = [...r].sort((a, b) => (a[sort.k] > b[sort.k] ? 1 : a[sort.k] < b[sort.k] ? -1 : 0) * sort.d);
    return r;
  }, [rows, q, sort, cols]);
  const cell = (c: Col<T>, r: T) => {
    if (c.render) return c.render(r);
    const v = r[c.key];
    const inner = c.kind === "money" ? money(v, c.cur?.(r)) : c.kind === "date" ? dt(v) : c.kind === "badge" ? <Badge v={v} /> : v ?? "—";
    return c.link ? <Link to={c.link(r)}>{inner}</Link> : inner;
  };
  const totals = cols.some((c) => c.total);
  return (
    <div>
      {filter && rows.length > 8 && <input className="filter" placeholder="Filtrer…" value={q} onChange={(e) => setQ(e.target.value)} />}
      <div className="table-wrap">
        <table>
          <thead><tr>
            {selectable && <th></th>}
            {cols.map((c) => <th key={c.key} className={c.kind === "money" || c.kind === "num" || c.align ? "r" : ""}
              onClick={() => setSort((s) => ({ k: c.key, d: s?.k === c.key && s.d === 1 ? -1 : 1 }))}>{c.label}{sort?.k === c.key ? (sort.d === 1 ? " ▲" : " ▼") : ""}</th>)}
          </tr></thead>
          <tbody>
            {view.length === 0 && <tr><td colSpan={cols.length + (selectable ? 1 : 0)} className="muted center">{empty}</td></tr>}
            {view.map((r, i) => (
              <tr key={r.id ?? r.invoice_id ?? i} className={onRow ? "click" : ""} onClick={() => onRow?.(r)}>
                {selectable && <td onClick={(e) => e.stopPropagation()}>{selectable(r) && <input type="checkbox" checked={selected?.has(r.invoice_id ?? r.id)}
                  onChange={(e) => { const s = new Set(selected); const k = r.invoice_id ?? r.id; e.target.checked ? s.add(k) : s.delete(k); onSelect?.(s); }} />}</td>}
                {cols.map((c) => <td key={c.key} className={c.kind === "money" || c.kind === "num" || c.align ? "r" : ""}>{cell(c, r)}</td>)}
              </tr>
            ))}
          </tbody>
          {totals && view.length > 0 && <tfoot><tr>{selectable && <td></td>}{cols.map((c, i) => <td key={c.key} className={c.total ? "r" : ""}>
            {c.total ? money(view.reduce((s, r) => s + Number(r[c.key] || 0), 0)) : i === 0 ? "Total" : ""}</td>)}</tr></tfoot>}
        </table>
      </div>
    </div>
  );
}
