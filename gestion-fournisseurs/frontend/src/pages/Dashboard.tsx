import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Link } from "react-router-dom";
import { api } from "../api";
import { money, num } from "../format";
import { Card, DataTable, Kpi, Loading, useLoad } from "../components/ui";

const BUCKETS: [string, string][] = [["non_echu", "Non échu"], ["1_30", "1-30 j"], ["31_60", "31-60 j"], ["61_90", "61-90 j"], ["91_180", "91-180 j"], ["plus_180", "> 180 j"]];
const kfmt = (v: number) => new Intl.NumberFormat("fr-TN", { notation: "compact" }).format(v);

export default function Dashboard() {
  const [d, , , err] = useLoad(() => api.get("/api/reports/dashboard"), []);
  if (!d) return <Loading err={err} />;
  const k = d.indicateurs;
  return (
    <div>
      <h2>Tableau de bord fournisseurs</h2>
      <div className="grid g4">
        <Kpi label="Total dettes fournisseurs" value={money(k.total_dettes)} hint="TND, factures validées" />
        <Kpi label="Dettes échues" value={money(k.dettes_echues)} tone={k.dettes_echues > 0 ? "err" : "ok"} />
        <Kpi label="Échéance à 7 jours" value={money(d.echeance_7_jours)} tone="warn" />
        <Kpi label="Dettes non échues" value={money(k.dettes_non_echues)} />
        <Kpi label="Paiements prévus" value={money(d.paiements_prevus)} hint="en préparation / autorisés" />
        <Kpi label="Paiements effectués (mois)" value={money(d.paiements_effectues_mois)} />
        <Kpi label="Engagements non facturés" value={money(k.engagements_non_factures)} hint="commandes approuvées" />
        <Kpi label="Trésorerie disponible" value={money(d.tresorerie_disponible)} hint="relevés − paiements émis non débités" />
        <Kpi label="DPO" value={k.dpo_jours !== null ? `${num(k.dpo_jours)} j` : "—"} hint="dettes / achats TTC × 365" />
        <Kpi label="Délai moyen de paiement" value={k.delai_moyen_paiement_jours !== null ? `${num(k.delai_moyen_paiement_jours)} j` : "—"} />
        <Kpi label="Paiement à échéance" value={k.taux_paiement_a_echeance_pct !== null ? `${num(k.taux_paiement_a_echeance_pct)} %` : "—"} />
        <Kpi label="Factures à valider / litiges" value={<><Link to="/factures?statut=en_attente_validation">{k.factures_en_attente_validation}</Link> / <Link to="/litiges">{d.litiges_ouverts}</Link></>} />
      </div>
      <div className="grid g2" style={{ marginTop: 14 }}>
        <Card title="Ancienneté des dettes (TND)">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={BUCKETS.map(([k2, l]) => ({ tranche: l, montant: Number(d.anciennete[k2]) }))}>
              <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="tranche" /><YAxis tickFormatter={kfmt} />
              <Tooltip formatter={(v: any) => money(v)} /><Bar dataKey="montant" fill="#2e5c8a" />
            </BarChart>
          </ResponsiveContainer>
        </Card>
        <Card title="Prévisions de décaissements — 12 mois (TND)">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={d.previsions_mensuelles}>
              <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="mois" /><YAxis tickFormatter={kfmt} /><Tooltip formatter={(v: any) => money(v)} /><Legend />
              <Bar dataKey="certain" stackId="a" fill="#1f3a5f" name="Certain" /><Bar dataKey="probable" stackId="a" fill="#6c9bd2" name="Probable" />
              <Bar dataKey="conditionnel" stackId="a" fill="#c8963e" name="Conditionnel (litiges)" />
            </BarChart>
          </ResponsiveContainer>
        </Card>
        <Card title="Évolution mensuelle des dettes (TND)">
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={k.evolution_mensuelle}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="mois" /><YAxis tickFormatter={kfmt} />
              <Tooltip formatter={(v: any) => money(v)} /><Line dataKey="dettes" stroke="#2e5c8a" strokeWidth={2} name="Dettes" /></LineChart>
          </ResponsiveContainer>
        </Card>
        <Card title="Principaux fournisseurs créanciers" actions={<span className="muted">Top 5 : {k.concentration_top5_pct ?? "—"} % · HHI {num(k.indice_hhi, 0)}</span>}>
          <DataTable filter={false} rows={k.principaux_creanciers} cols={[
            { key: "fournisseur", label: "Fournisseur", link: (r) => `/fournisseurs/${r.supplier_id}` },
            { key: "montant", label: "Dette (TND)", kind: "money" }, { key: "part_pct", label: "Part %", kind: "num" }]} />
        </Card>
      </div>
      <Card title="Horizons de décaissement">
        <DataTable filter={false} rows={d.previsions} cols={[
          { key: "jours", label: "Horizon (jours)" }, { key: "certain", label: "Certain", kind: "money" },
          { key: "probable", label: "Probable", kind: "money" }, { key: "conditionnel", label: "Conditionnel", kind: "money" },
          { key: "total", label: "Total", kind: "money" }]} />
      </Card>
      <Card title="Alertes prioritaires">
        {d.alertes.length === 0 ? <div className="muted">Aucune alerte.</div> :
          d.alertes.map((a: any, i: number) => <Link key={i} to={a.lien.split("?")[0]} className={`al ${a.gravite}`}>{a.message}</Link>)}
      </Card>
    </div>
  );
}
