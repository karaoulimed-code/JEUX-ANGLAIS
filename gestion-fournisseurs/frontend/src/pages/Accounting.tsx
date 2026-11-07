import { useState } from "react";
import { api, download } from "../api";
import { dt, money, today } from "../format";
import { Badge, Card, DataTable, Field, Kpi, Loading, Modal, Tabs, useAction, useCan, useLoad } from "../components/ui";

export default function Accounting() {
  const [tab, setTab] = useState("ecritures");
  const [status, setStatus] = useState("proposee");
  const [journal, setJournal] = useState("");
  const [rows, reload, , err] = useLoad(() => api.get(`/api/accounting/entries?status=${status}&journal=${journal}`), [status, journal]);
  const [asOf, setAsOf] = useState(today());
  const [ext, setExt] = useState("");
  const [rec] = useLoad(() => tab === "rappro" ? api.get(`/api/accounting/reconciliation?as_of=${asOf}${ext ? `&external_gl_balance=${ext}` : ""}`) : Promise.resolve(null), [tab, asOf, ext]);
  const [bal] = useLoad(() => tab === "soldes" ? api.get(`/api/accounting/balances?as_of=${asOf}`) : Promise.resolve(null), [tab, asOf]);
  const [fnp, reloadFnp] = useLoad(() => tab === "cloture" ? api.get("/api/accounting/closing/fnp") : Promise.resolve(null), [tab]);
  const [fx] = useLoad(() => tab === "cloture" ? api.get(`/api/accounting/closing/fx-revaluation?as_of=${asOf}`).catch((e) => ({ erreur: e.message })) : Promise.resolve(null), [tab, asOf]);
  const [sel, setSel] = useState<Set<any>>(new Set());
  const [view, setView] = useState<any>(null);
  const can = useCan();
  const act = useAction();
  return (
    <div>
      <div className="row between"><h2>Comptabilité fournisseurs</h2>
        <button className="btn" onClick={() => act(() => download("/api/accounting/export?only_validated=true"))}>Exporter les écritures validées (CSV)</button></div>
      <div className="alert info">Les écritures sont proposées automatiquement à chaque événement (facture validée, décaissement, rejet, imputation) et
        validées par le responsable comptable. Une écriture validée n'est jamais modifiée : toute correction passe par contre-passation.</div>
      <Tabs active={tab} onChange={setTab} tabs={[["ecritures", "Écritures"], ["rappro", "Rapprochement auxiliaire / général"], ["soldes", "Soldes des comptes"], ["cloture", "Travaux de clôture"]]} />
      {tab === "ecritures" && <Card actions={can("accounting.validate") && sel.size > 0 &&
        <button className="btn ok" onClick={async () => { if (await act(() => api.post("/api/accounting/entries/validate", { ids: [...sel] }), "Écritures validées")) { setSel(new Set()); reload(); } }}>Valider la sélection ({sel.size})</button>}>
        <div className="row gap" style={{ marginBottom: 8 }}>
          <select value={status} onChange={(e) => setStatus(e.target.value)}><option value="">Toutes</option><option value="proposee">Proposées</option><option value="validee">Validées</option></select>
          <select value={journal} onChange={(e) => setJournal(e.target.value)}><option value="">Tous journaux</option><option value="ACH">Achats</option><option value="REG">Règlements</option><option value="OD">Opérations diverses</option></select>
        </div>
        {!rows ? <Loading err={err} /> : <DataTable rows={rows} onRow={setView} selectable={(r) => r.status === "proposee"} selected={sel} onSelect={setSel} cols={[
          { key: "number", label: "N°" }, { key: "journal", label: "Journal" }, { key: "entry_date", label: "Date", kind: "date" }, { key: "label", label: "Libellé" },
          { key: "total_debit", label: "Débit", kind: "money", total: true }, { key: "total_credit", label: "Crédit", kind: "money", total: true },
          { key: "status", label: "Statut", kind: "badge" }]} />}
      </Card>}
      {tab === "rappro" && <Card>
        <div className="row gap"><Field label="Date d'arrêté"><input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} /></Field>
          <Field label="Solde 401 du logiciel comptable externe (optionnel)"><input type="number" value={ext} onChange={(e) => setExt(e.target.value)} /></Field></div>
        {!rec ? <Loading /> : <>
          <div className="grid g4" style={{ marginTop: 10 }}>
            <Kpi label="Solde auxiliaire (pièces)" value={money(rec.solde_auxiliaire)} />
            <Kpi label="Solde général (écritures)" value={money(rec.solde_general_toutes_ecritures)} hint={`dont non validées ${money(rec.ecritures_non_validees)}`} />
            <Kpi label="Écart" value={money(rec.ecart)} tone={rec.concordant ? "ok" : "err"} hint={rec.concordant ? "Concordant" : "À analyser"} />
            {rec.solde_logiciel_comptable_externe !== undefined && <Kpi label="Écart avec la comptabilité externe" value={money(rec.ecart_externe)} tone={Number(rec.ecart_externe) === 0 ? "ok" : "err"} />}
          </div>
          {rec.ecarts_par_fournisseur.length > 0 && <DataTable rows={rec.ecarts_par_fournisseur} cols={[{ key: "fournisseur", label: "Fournisseur" },
            { key: "auxiliaire", label: "Auxiliaire", kind: "money" }, { key: "general", label: "Général", kind: "money" }, { key: "ecart", label: "Écart", kind: "money" }]} />}
          <p className="muted">Un écart temporaire peut provenir d'une écriture d'actualisation des dettes en devises (extournée le lendemain).</p>
        </>}
      </Card>}
      {tab === "soldes" && <Card>{!bal ? <Loading /> : <DataTable filter={false} rows={bal} cols={[{ key: "compte", label: "Compte" }, { key: "cle", label: "Rôle" },
        { key: "solde_crediteur", label: "Solde créditeur (négatif = débiteur)", kind: "money" }]} />}</Card>}
      {tab === "cloture" && <div className="grid g2">
        <Card title="Factures non parvenues (réceptions non facturées)" actions={can("accounting.validate") && fnp?.lignes?.length > 0 &&
          <button className="btn" onClick={async () => { if (await act(() => api.post(`/api/accounting/closing/fnp?as_of=${asOf}`), "Écriture FNP et extourne proposées")) reloadFnp(); }}>Générer l'écriture au {dt(asOf)}</button>}>
          {!fnp ? <Loading /> : <><DataTable rows={fnp.lignes} cols={[{ key: "bc", label: "BC" }, { key: "description", label: "Article" }, { key: "compte", label: "Compte" },
            { key: "montant_ht_tnd", label: "HT TND", kind: "money", total: true }, { key: "tva", label: "TVA", kind: "money", total: true }]} /></>}
        </Card>
        <Card title="Actualisation des dettes en devises" actions={can("accounting.validate") && fx?.lignes?.length > 0 &&
          <button className="btn" onClick={() => act(() => api.post(`/api/accounting/closing/fx-revaluation?as_of=${asOf}`), "Écriture d'actualisation et extourne proposées")}>Générer l'écriture</button>}>
          <Field label="Date de clôture"><input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} /></Field>
          {!fx ? <Loading /> : fx.erreur ? <div className="alert warn">{fx.erreur}</div> : <>
            <DataTable rows={fx.lignes} cols={[{ key: "ref", label: "Facture" }, { key: "devise", label: "Devise" }, { key: "solde_devise", label: "Solde", kind: "money" },
              { key: "cours_historique", label: "Cours historique" }, { key: "cours_cloture", label: "Cours clôture" }, { key: "ecart_tnd", label: "Écart TND", kind: "money", total: true }]} />
            <p className="muted">{fx.note}</p></>}
        </Card>
      </div>}
      {view && <Modal wide title={`Écriture ${view.number} — ${view.journal} du ${dt(view.entry_date)}`} onClose={() => setView(null)}>
        <p>{view.label} <Badge v={view.status} /></p>
        <DataTable filter={false} rows={view.lines} cols={[{ key: "account_code", label: "Compte" }, { key: "auxiliaire", label: "Auxiliaire" },
          { key: "label", label: "Libellé" }, { key: "debit", label: "Débit", kind: "money", total: true }, { key: "credit", label: "Crédit", kind: "money", total: true }]} />
      </Modal>}
    </div>
  );
}
