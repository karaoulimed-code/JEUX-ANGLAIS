import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";
import { dt, money, today } from "../format";
import { t } from "../i18n";
import { Card, DataTable, ExportButtons, Field, Kpi, Loading, Tabs, useLoad } from "../components/ui";

export function Aging() {
  const [asOf, setAsOf] = useState(today());
  const [cur, setCur] = useState("");
  const [cat, setCat] = useState("");
  const [tab, setTab] = useState("synthese");
  const [d, , , err] = useLoad(() => api.get(`/api/reports/aging?as_of=${asOf}&currency=${cur}&category=${cat}`), [asOf, cur, cat]);
  return (
    <div>
      <div className="row between"><h2>Échéancier et balance âgée</h2>
        <div className="row gap"><span className="muted">Balance âgée :</span><ExportButtons name="balance-agee" params={`&as_of=${asOf}`} />
          <span className="muted">Échéancier :</span><ExportButtons name="echeancier" params={`&as_of=${asOf}`} /></div></div>
      <Card>
        <div className="row gap">
          <Field label="Date d'arrêté"><input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} /></Field>
          <Field label="Devise"><select value={cur} onChange={(e) => setCur(e.target.value)}><option value="">Toutes</option><option>TND</option><option>EUR</option><option>USD</option></select></Field>
          <Field label="Catégorie"><select value={cat} onChange={(e) => setCat(e.target.value)}><option value="">Toutes</option>
            {["strategique", "regulier", "occasionnel", "critique", "a_risque"].map((c) => <option key={c} value={c}>{t(c)}</option>)}</select></Field>
        </div>
      </Card>
      {!d ? <Loading err={err} /> : <>
        <div className="grid g4">
          <Kpi label="Total dettes" value={money(d.totaux.total_brut)} /><Kpi label="Non échu" value={money(d.totaux.non_echu)} tone="ok" />
          <Kpi label="Échu" value={money(Number(d.totaux.total_brut) - Number(d.totaux.non_echu))} tone="err" />
          <Kpi label="Solde net (après avoirs et avances)" value={money(d.totaux.total_net)} hint={`dont litiges ${money(d.totaux.dont_litiges)}`} />
        </div>
        <Tabs active={tab} onChange={setTab} tabs={[["synthese", "Par fournisseur"], ["detail", "Détail des factures"]]} />
        <Card>{tab === "synthese" ? <DataTable rows={d.lignes} cols={[
          { key: "code", label: "Code", link: (r) => `/fournisseurs/${r.supplier_id}` }, { key: "fournisseur", label: "Fournisseur" },
          { key: "non_echu", label: "Non échu", kind: "money", total: true }, { key: "1_30", label: "1-30 j", kind: "money", total: true },
          { key: "31_60", label: "31-60 j", kind: "money", total: true }, { key: "61_90", label: "61-90 j", kind: "money", total: true },
          { key: "91_180", label: "91-180 j", kind: "money", total: true }, { key: "plus_180", label: "> 180 j", kind: "money", total: true },
          { key: "total_brut", label: "Total", kind: "money", total: true }, { key: "avoirs_non_imputes", label: "Avoirs", kind: "money", total: true },
          { key: "avances_non_imputees", label: "Avances", kind: "money", total: true }, { key: "total_net", label: "Net", kind: "money", total: true }]} />
          : <DataTable rows={d.details} cols={[{ key: "ref", label: "Facture", link: (r) => `/factures/${r.invoice_id}` }, { key: "numero", label: "N°" },
            { key: "fournisseur", label: "Fournisseur" }, { key: "date", label: "Date", kind: "date" }, { key: "echeance", label: "Échéance", kind: "date" },
            { key: "solde_devise", label: "Solde devise", kind: "money", cur: (r) => r.devise }, { key: "solde_tnd", label: "Solde TND", kind: "money", total: true },
            { key: "retard_jours", label: "Retard (j)", kind: "num" }, { key: "tranche", label: "Tranche" }]} />}</Card>
      </>}
    </div>
  );
}

export function Forecast() {
  const [d, , , err] = useLoad(() => api.get("/api/reports/forecast"), []);
  if (!d) return <Loading err={err} />;
  return (
    <div>
      <div className="row between"><h2>Prévisions de décaissements fournisseurs</h2><ExportButtons name="previsions" /></div>
      <div className="alert info">{d.conventions}</div>
      <div className="grid g4">{d.horizons.map((h: any) => <Kpi key={h.jours} label={`À ${h.jours} jours`} value={money(h.total)}
        hint={`certain ${money(h.certain)} · probable ${money(h.probable)} · conditionnel ${money(h.conditionnel)}`}
        tone={Number(h.certain) > Number(d.tresorerie_disponible) ? "err" : undefined} />)}
        <Kpi label="Trésorerie disponible" value={money(d.tresorerie_disponible)} tone="ok" /></div>
      <Card title="Profil mensuel sur 12 mois (TND)">
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={d.mensuel}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="mois" /><YAxis /><Tooltip formatter={(v: any) => money(v)} /><Legend />
            <Bar dataKey="certain" stackId="a" fill="#1f3a5f" name="Certain" /><Bar dataKey="probable" stackId="a" fill="#6c9bd2" name="Probable" />
            <Bar dataKey="conditionnel" stackId="a" fill="#c8963e" name="Conditionnel" /></BarChart>
        </ResponsiveContainer>
      </Card>
      <Card title="Détail des décaissements prévus"><DataTable rows={d.detail} cols={[{ key: "date", label: "Date", kind: "date" },
        { key: "categorie", label: "Catégorie" }, { key: "source", label: "Origine" }, { key: "ref", label: "Référence" },
        { key: "montant", label: "Montant TND", kind: "money", total: true }, { key: "en_retard", label: "", render: (r) => r.en_retard ? <span className="badge err">en retard</span> : "" }]} /></Card>
      <p className="muted">Pour arbitrer entre paiement anticipé, à échéance ou report négocié : Règlements › Préparation & optimisation. Données au {dt(d.date)}.</p>
    </div>
  );
}
