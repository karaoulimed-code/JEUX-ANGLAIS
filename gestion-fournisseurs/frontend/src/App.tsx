import { useEffect, useState } from "react";
import { BrowserRouter, Link, NavLink, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { api, getToken, setToken, setUnauthorizedHandler } from "./api";
import { lang, setLang, t, Lang } from "./i18n";
import { Me, MeContext, ToastProvider, useLoad } from "./components/ui";
import Dashboard from "./pages/Dashboard";
import { SupplierDetail, Suppliers, Risk } from "./pages/Suppliers";
import { OrderDetail, Purchasing } from "./pages/Purchasing";
import { InvoiceDetail, Invoices } from "./pages/Invoices";
import { PaymentDetail, Payments, Treasury } from "./pages/Payments";
import Disputes from "./pages/Disputes";
import { Aging, Forecast } from "./pages/Analysis";
import Accounting from "./pages/Accounting";
import Reports from "./pages/Reports";
import { Audit, Settings } from "./pages/Settings";

function Login({ onLogin }: { onLogin: (m: Me) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setErr("");
    try {
      const r = await api.post("/api/auth/login", { email, password });
      setToken(r.access_token); onLogin(r.user);
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  return (
    <div className="login-bg">
      <form className="login card" onSubmit={submit}>
        <h1>{t("app")}</h1>
        <p className="muted">Cycle fournisseurs intégré — PME tunisiennes</p>
        <label className="field"><span>E-mail</span><input autoFocus type="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
        <label className="field"><span>Mot de passe</span><input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
        {err && <div className="alert err">{err}</div>}
        <button className="btn primary" disabled={busy}>{busy ? "Connexion…" : "Se connecter"}</button>
      </form>
    </div>
  );
}

function Search() {
  const [q, setQ] = useState("");
  const [res, setRes] = useState<any[]>([]);
  const nav = useNavigate();
  useEffect(() => {
    if (q.length < 2) { setRes([]); return; }
    const h = setTimeout(() => api.get(`/api/reports/search?q=${encodeURIComponent(q)}`).then(setRes).catch(() => {}), 250);
    return () => clearTimeout(h);
  }, [q]);
  return (
    <div className="search">
      <input placeholder={t("search")} value={q} onChange={(e) => setQ(e.target.value)} aria-label="Recherche globale" />
      {res.length > 0 && <div className="search-res">{res.map((r) => (
        <button key={r.type + r.id} onClick={() => { setQ(""); setRes([]); nav(r.lien); }}><span className="badge info">{r.type}</span> {r.libelle}</button>))}
      </div>}
    </div>
  );
}

function Bell() {
  const [alerts] = useLoad(() => api.get("/api/reports/alerts"), []);
  const [open, setOpen] = useState(false);
  const n = alerts?.filter((a: any) => a.gravite === "haute").length || 0;
  return (
    <div className="bell">
      <button className="btn ghost" onClick={() => setOpen(!open)} aria-label="Alertes">🔔{n > 0 && <span className="dot">{n}</span>}</button>
      {open && <div className="bell-pop">{(alerts || []).slice(0, 25).map((a: any, i: number) => (
        <Link key={i} to={a.lien.split("?")[0]} onClick={() => setOpen(false)} className={`al ${a.gravite}`}>{a.message}</Link>))}
        {alerts?.length === 0 && <div className="muted pad">Aucune alerte.</div>}</div>}
    </div>
  );
}

const NAV: [string, string, string][] = [
  ["/", "dashboard", "read"], ["/fournisseurs", "suppliers", "read"], ["/achats", "purchasing", "read"],
  ["/factures", "invoices", "read"], ["/reglements", "payments", "read"], ["/tresorerie", "treasury", "read"],
  ["/litiges", "disputes", "read"], ["/echeancier", "aging", "read"], ["/previsions", "forecast", "treasury.read"],
  ["/risques", "risk", "read"], ["/comptabilite", "accounting", "accounting.read"], ["/etats", "reports", "read"],
  ["/parametres", "settings", "read"], ["/audit", "audit", "audit.read"],
];

function Shell({ me, onLogout }: { me: Me; onLogout: () => void }) {
  const [menu, setMenu] = useState(false);
  const [, force] = useState(0);
  return (
    <div className="shell">
      <aside className={menu ? "open" : ""}>
        <div className="brand">AP<span>·TN</span></div>
        <nav>{NAV.filter(([, , p]) => me.permissions.includes(p)).map(([to, k]) => (
          <NavLink key={to} to={to} end={to === "/"} onClick={() => setMenu(false)}>{t(k)}</NavLink>))}</nav>
        <div className="aside-foot muted">{me.company?.name}{me.company?.is_demo && <div className="badge warn">Démonstration</div>}</div>
      </aside>
      <div className="main">
        <header className="top">
          <button className="btn ghost burger" onClick={() => setMenu(!menu)} aria-label="Menu">☰</button>
          <Search />
          <Bell />
          <select value={lang()} onChange={(e) => { setLang(e.target.value as Lang); force((x) => x + 1); }} aria-label="Langue">
            <option value="fr">FR</option><option value="ar">ع</option><option value="en">EN</option>
          </select>
          <div className="who"><b>{me.full_name}</b><small>{me.role_label}</small></div>
          <button className="btn ghost" onClick={onLogout}>{t("logout")}</button>
        </header>
        <main className="content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/fournisseurs" element={<Suppliers />} />
            <Route path="/fournisseurs/:id" element={<SupplierDetail />} />
            <Route path="/achats" element={<Purchasing />} />
            <Route path="/achats/commandes/:id" element={<OrderDetail />} />
            <Route path="/factures" element={<Invoices />} />
            <Route path="/factures/:id" element={<InvoiceDetail />} />
            <Route path="/reglements" element={<Payments />} />
            <Route path="/reglements/:id" element={<PaymentDetail />} />
            <Route path="/tresorerie" element={<Treasury />} />
            <Route path="/litiges" element={<Disputes />} />
            <Route path="/echeancier" element={<Aging />} />
            <Route path="/previsions" element={<Forecast />} />
            <Route path="/risques" element={<Risk />} />
            <Route path="/comptabilite" element={<Accounting />} />
            <Route path="/etats" element={<Reports />} />
            <Route path="/parametres" element={<Settings />} />
            <Route path="/audit" element={<Audit />} />
            <Route path="*" element={<Navigate to="/" />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}

export default function App() {
  const [me, setMe] = useState<Me | null>(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    setUnauthorizedHandler(() => setMe(null));
    if (getToken()) api.get("/api/auth/me").then(setMe).catch(() => setToken(null)).finally(() => setReady(true));
    else setReady(true);
  }, []);
  const logout = async () => { try { await api.post("/api/auth/logout"); } catch {} setToken(null); setMe(null); };
  if (!ready) return null;
  return (
    <ToastProvider>
      {!me ? <Login onLogin={setMe} /> : (
        <MeContext.Provider value={me}>
          <BrowserRouter><Shell me={me} onLogout={logout} /></BrowserRouter>
        </MeContext.Provider>
      )}
    </ToastProvider>
  );
}
