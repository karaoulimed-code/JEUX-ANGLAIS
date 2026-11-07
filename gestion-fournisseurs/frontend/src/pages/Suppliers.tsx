import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { dt, money, today } from "../format";
import { t } from "../i18n";
import { Badge, Card, DataTable, ExportButtons, Field, Loading, Modal, Tabs, useAction, useCan, useLoad } from "../components/ui";

const EMPTY = { code: "", legal_name: "", trade_name: "", tax_id: "", address: "", city: "", phone: "", email: "", contact_name: "",
  sector: "", supply_nature: "", category: "regulier", vat_regime: "assujetti", rs_code: "RS_ACHATS_1_5", currency: "TND",
  payment_terms_days: 30, payment_terms_type: "net", early_discount_pct: 0, early_discount_days: 0, late_penalty_pct: 0,
  credit_limit: "", default_account: "", is_resident: true, notes: "" };

export function SupplierForm({ initial, onDone, edit }: { initial?: any; onDone: () => void; edit?: boolean }) {
  const [f, setF] = useState<any>({ ...EMPTY, ...(initial || {}) });
  const [dups, setDups] = useState<any[]>([]);
  const [rates] = useLoad(() => api.get("/api/admin/tax-rates"), []);
  const act = useAction();
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });
  const check = async () => { if (!edit && f.legal_name.length > 2) setDups(await api.post("/api/suppliers/check-duplicates", { legal_name: f.legal_name, tax_id: f.tax_id })); };
  const save = async (force = false) => {
    const body: any = { ...f, credit_limit: f.credit_limit === "" ? null : f.credit_limit, rs_code: f.rs_code || null,
      default_account: f.default_account || null };
    Object.keys(body).forEach((k) => !(k in EMPTY) && delete body[k]);
    const r = await act(() => edit ? api.patch(`/api/suppliers/${initial.id}`, body) : api.post(`/api/suppliers${force ? "?force=true" : ""}`, body),
      edit ? "Fiche mise à jour" : "Fournisseur créé (en attente d'approbation)");
    if (r) onDone();
  };
  return (
    <div>
      <div className="form-grid">
        <Field label="Code *"><input value={f.code} onChange={set("code")} disabled={edit} /></Field>
        <Field label="Raison sociale *"><input value={f.legal_name} onChange={set("legal_name")} onBlur={check} /></Field>
        <Field label="Nom commercial"><input value={f.trade_name || ""} onChange={set("trade_name")} /></Field>
        <Field label="Matricule fiscal" hint="ex. 1234567/A/M/000"><input value={f.tax_id || ""} onChange={set("tax_id")} onBlur={check} /></Field>
        <Field label="Adresse"><input value={f.address || ""} onChange={set("address")} /></Field>
        <Field label="Ville"><input value={f.city || ""} onChange={set("city")} /></Field>
        <Field label="Téléphone"><input value={f.phone || ""} onChange={set("phone")} /></Field>
        <Field label="E-mail"><input value={f.email || ""} onChange={set("email")} /></Field>
        <Field label="Contact"><input value={f.contact_name || ""} onChange={set("contact_name")} /></Field>
        <Field label="Secteur d'activité"><input value={f.sector || ""} onChange={set("sector")} /></Field>
        <Field label="Nature des biens / services"><input value={f.supply_nature || ""} onChange={set("supply_nature")} /></Field>
        <Field label="Catégorie"><select value={f.category} onChange={set("category")}>
          {["strategique", "regulier", "occasionnel", "critique", "a_risque"].map((c) => <option key={c} value={c}>{t(c)}</option>)}</select></Field>
        <Field label="Régime TVA"><select value={f.vat_regime} onChange={set("vat_regime")}>
          <option value="assujetti">Assujetti</option><option value="non_assujetti">Non assujetti</option><option value="exonere">Exonéré</option><option value="forfaitaire">Forfaitaire</option></select></Field>
        <Field label="Retenue à la source"><select value={f.rs_code || ""} onChange={set("rs_code")}><option value="">Aucune</option>
          {(rates || []).filter((r: any) => r.kind === "RS").map((r: any) => <option key={r.id} value={r.code}>{r.label}</option>)}</select></Field>
        <Field label="Devise"><select value={f.currency} onChange={set("currency")}><option>TND</option><option>EUR</option><option>USD</option></select></Field>
        <Field label="Résident"><input type="checkbox" checked={f.is_resident} onChange={set("is_resident")} /></Field>
        <Field label="Délai de paiement (jours)"><input type="number" value={f.payment_terms_days} onChange={set("payment_terms_days")} /></Field>
        <Field label="Mode de calcul"><select value={f.payment_terms_type} onChange={set("payment_terms_type")}><option value="net">Net (date facture + délai)</option><option value="fin_de_mois">Fin de mois</option></select></Field>
        <Field label="Escompte paiement anticipé (%)"><input type="number" step="0.01" value={f.early_discount_pct} onChange={set("early_discount_pct")} /></Field>
        <Field label="… si payé sous (jours)"><input type="number" value={f.early_discount_days} onChange={set("early_discount_days")} /></Field>
        <Field label="Pénalités de retard contractuelles (%/an)"><input type="number" step="0.01" value={f.late_penalty_pct} onChange={set("late_penalty_pct")} /></Field>
        <Field label="Plafond d'engagement (TND)"><input type="number" value={f.credit_limit ?? ""} onChange={set("credit_limit")} /></Field>
        <Field label="Compte de charge par défaut"><input value={f.default_account || ""} onChange={set("default_account")} placeholder="ex. 6061" /></Field>
      </div>
      <Field label="Conditions contractuelles / notes"><textarea rows={2} value={f.notes || ""} onChange={set("notes")} /></Field>
      {dups.length > 0 && <div className="alert warn">Doublons potentiels : {dups.map((d) => `${d.code} ${d.legal_name} (${d.motifs.join(", ")})`).join(" ; ")}</div>}
      <div className="modal-actions">
        {dups.some((d) => d.motifs.includes("matricule fiscal identique")) && !edit &&
          <button className="btn danger" onClick={() => save(true)}>Créer malgré le doublon</button>}
        <button className="btn primary" onClick={() => save()}>Enregistrer</button>
      </div>
    </div>
  );
}

export function Suppliers() {
  const [q, setQ] = useState({ category: "", status: "" });
  const [rows, reload, , err] = useLoad(() => api.get(`/api/suppliers?category=${q.category}&status=${q.status}`), [q]);
  const [open, setOpen] = useState(false);
  const can = useCan();
  const nav = useNavigate();
  return (
    <div>
      <div className="row between"><h2>Fichier fournisseurs</h2>
        {can("supplier.write") && <button className="btn primary" onClick={() => setOpen(true)}>+ Nouveau fournisseur</button>}</div>
      <Card>
        <div className="row gap" style={{ marginBottom: 8 }}>
          <select value={q.category} onChange={(e) => setQ({ ...q, category: e.target.value })}><option value="">Toutes catégories</option>
            {["strategique", "regulier", "occasionnel", "critique", "a_risque"].map((c) => <option key={c} value={c}>{t(c)}</option>)}</select>
          <select value={q.status} onChange={(e) => setQ({ ...q, status: e.target.value })}><option value="">Tous statuts</option>
            {["en_attente", "actif", "bloque", "inactif"].map((c) => <option key={c} value={c}>{t(c)}</option>)}</select>
        </div>
        {!rows ? <Loading err={err} /> : <DataTable rows={rows} onRow={(r) => nav(`/fournisseurs/${r.id}`)} cols={[
          { key: "code", label: "Code" }, { key: "legal_name", label: "Raison sociale" }, { key: "tax_id", label: "Matricule fiscal" },
          { key: "category", label: "Catégorie", kind: "badge" }, { key: "status", label: "Statut", kind: "badge" },
          { key: "currency", label: "Devise" }, { key: "payment_terms_days", label: "Délai (j)", kind: "num" },
          { key: "rib", label: "RIB", render: (r) => r.rib_a_verifier ? <Badge v="a_verifier" /> : r.rib_verifie ? <Badge v="verifie" /> : <span className="muted">—</span> },
          { key: "solde_du_tnd", label: "Solde dû (TND)", kind: "money", total: true }]} />}
      </Card>
      {open && <Modal wide title="Nouveau fournisseur" onClose={() => setOpen(false)}><SupplierForm onDone={() => { setOpen(false); reload(); }} /></Modal>}
    </div>
  );
}

export function SupplierDetail() {
  const { id } = useParams();
  const [s, reload, , err] = useLoad(() => api.get(`/api/suppliers/${id}`), [id]);
  const [tab, setTab] = useState("fiche");
  const [modal, setModal] = useState<string | null>(null);
  const [form, setForm] = useState<any>({});
  const can = useCan();
  const act = useAction();
  if (!s) return <Loading err={err} />;
  const post = async (url: string, body: any, ok: string) => { if (await act(() => api.post(url, body), ok)) { setModal(null); setForm({}); reload(); } };
  const set = (k: string) => (e: any) => setForm({ ...form, [k]: e.target.value });
  return (
    <div>
      <div className="row between">
        <h2>{s.code} — {s.legal_name} <Badge v={s.status} /> <Badge v={s.category} /></h2>
        <div className="row gap">
          {can("supplier.approve") && s.status !== "actif" && <button className="btn ok" onClick={() => post(`/api/suppliers/${id}/status`, { status: "actif" }, "Fournisseur approuvé")}>Approuver / activer</button>}
          {can("supplier.approve") && s.status === "actif" && <button className="btn danger" onClick={() => post(`/api/suppliers/${id}/status`, { status: "bloque" }, "Fournisseur bloqué")}>Bloquer</button>}
          {can("supplier.write") && <button className="btn" onClick={() => setModal("edit")}>Modifier</button>}
        </div>
      </div>
      <Tabs active={tab} onChange={setTab} tabs={[["fiche", "Fiche"], ["banque", "Coordonnées bancaires"], ["factures", `Factures (${s.factures.length})`],
        ["reglements", "Règlements"], ["commandes", "Commandes"], ["contrats", "Contrats"], ["eval", "Incidents & évaluation"], ["risque", "Risque"]]} />
      {tab === "fiche" && <Card><dl className="kv">
        <dt>Matricule fiscal</dt><dd>{s.tax_id || "—"}</dd><dt>Nom commercial</dt><dd>{s.trade_name || "—"}</dd>
        <dt>Adresse</dt><dd>{[s.address, s.city, s.country].filter(Boolean).join(", ")}</dd>
        <dt>Contact</dt><dd>{[s.contact_name, s.phone, s.email].filter(Boolean).join(" · ") || "—"}</dd>
        <dt>Secteur / nature</dt><dd>{[s.sector, s.supply_nature].filter(Boolean).join(" — ") || "—"}</dd>
        <dt>Régime TVA / retenue</dt><dd>{s.vat_regime} / {s.rs_code || "aucune"}</dd>
        <dt>Conditions de paiement</dt><dd>{s.payment_terms_days} j {s.payment_terms_type === "fin_de_mois" ? "fin de mois" : "net"}
          {Number(s.early_discount_pct) > 0 && ` · escompte ${s.early_discount_pct} % sous ${s.early_discount_days} j`}
          {Number(s.late_penalty_pct) > 0 && ` · pénalités ${s.late_penalty_pct} %/an`}</dd>
        <dt>Devise</dt><dd>{s.currency}</dd><dt>Plafond d'engagement</dt><dd>{money(s.credit_limit)}</dd>
        <dt>Solde dû</dt><dd><b>{money(s.solde_du_tnd, "TND")}</b></dd><dt>Notes</dt><dd>{s.notes || "—"}</dd>
      </dl></Card>}
      {tab === "banque" && <Card title="Comptes bancaires" actions={can("supplier.write") && <button className="btn" onClick={() => setModal("rib")}>+ Nouveau RIB</button>}>
        <div className="alert info">Tout nouveau RIB remplace le précédent et doit être vérifié par une autre personne (contre-appel au fournisseur) avant tout virement.</div>
        <DataTable rows={s.comptes_bancaires} cols={[{ key: "bank_name", label: "Banque" }, { key: "rib", label: "RIB" }, { key: "iban", label: "IBAN" },
          { key: "currency", label: "Devise" }, { key: "status", label: "Statut", kind: "badge" }, { key: "verified_at", label: "Vérifié le", kind: "date" },
          { key: "verification_note", label: "Note" },
          { key: "a", label: "", render: (r) => r.status === "a_verifier" && can("supplier.bank_verify") ? <div className="row gap">
            <button className="btn sm ok" onClick={() => post(`/api/suppliers/bank-accounts/${r.id}/verify`, { accept: true, note: prompt("Note de vérification (contre-appel effectué auprès de …)") || "" }, "RIB vérifié")}>Valider</button>
            <button className="btn sm danger" onClick={() => post(`/api/suppliers/bank-accounts/${r.id}/verify`, { accept: false, note: prompt("Motif du rejet") || "" }, "RIB rejeté")}>Rejeter</button></div> : null }]} />
      </Card>}
      {tab === "factures" && <Card><DataTable rows={s.factures} cols={[{ key: "internal_ref", label: "Réf.", link: (r) => `/factures/${r.id}` },
        { key: "doc_type", label: "Type" }, { key: "supplier_number", label: "N°" }, { key: "invoice_date", label: "Date", kind: "date" },
        { key: "due_date", label: "Échéance", kind: "date" }, { key: "total_ttc", label: "TTC", kind: "money", cur: (r) => r.currency },
        { key: "solde", label: "Solde", kind: "money" }, { key: "statut", label: "Statut", kind: "badge" }]} /></Card>}
      {tab === "reglements" && <Card><DataTable rows={s.reglements} cols={[{ key: "number", label: "N°", link: (r) => `/reglements/${r.id}` },
        { key: "payment_date", label: "Date", kind: "date" }, { key: "method", label: "Moyen" }, { key: "reference", label: "Réf." },
        { key: "cash_amount", label: "Montant", kind: "money", cur: (r) => r.currency }, { key: "status", label: "Statut", kind: "badge" }]} /></Card>}
      {tab === "commandes" && <Card><DataTable rows={s.commandes} cols={[{ key: "number", label: "N°", link: (r) => `/achats/commandes/${r.id}` },
        { key: "order_date", label: "Date", kind: "date" }, { key: "total_ttc", label: "TTC", kind: "money" }, { key: "status", label: "Statut", kind: "badge" }]} /></Card>}
      {tab === "contrats" && <Card actions={can("supplier.write") && <button className="btn" onClick={() => setModal("contrat")}>+ Contrat</button>}>
        <DataTable rows={s.contrats} cols={[{ key: "reference", label: "Réf." }, { key: "subject", label: "Objet" }, { key: "start_date", label: "Début", kind: "date" },
          { key: "end_date", label: "Fin", kind: "date" }, { key: "recurring_amount_ttc", label: "Montant récurrent TTC", kind: "money" },
          { key: "frequency_months", label: "Périodicité (mois)" }, { key: "next_due_date", label: "Prochaine échéance", kind: "date" }]} /></Card>}
      {tab === "eval" && <div className="grid g2">
        <Card title="Incidents" actions={can("dispute.manage") && <button className="btn" onClick={() => setModal("incident")}>+ Incident</button>}>
          <DataTable rows={s.incidents} cols={[{ key: "incident_date", label: "Date", kind: "date" }, { key: "kind", label: "Type" },
            { key: "severity", label: "Gravité" }, { key: "description", label: "Description" }]} /></Card>
        <Card title="Évaluations" actions={can("supplier.evaluate") && <button className="btn" onClick={() => setModal("eval")}>+ Évaluation</button>}>
          <DataTable rows={s.evaluations} cols={[{ key: "period", label: "Période" }, { key: "quality", label: "Qualité" }, { key: "delivery", label: "Délais" },
            { key: "compliance", label: "Conformité" }, { key: "supply_risk", label: "Risque rupture" }, { key: "comment", label: "Commentaire" }]} /></Card>
      </div>}
      {tab === "risque" && <Card title={<>Score de risque : {s.risque?.score ?? "—"} / 100 <Badge v={s.risque?.niveau} /></>}>
        <p>Part des achats 12 mois : {s.risque?.part_achats_pct} %</p>
        <ul>{(s.risque?.facteurs || []).map((f: string, i: number) => <li key={i}>{f}</li>)}</ul>
        {!s.risque?.facteurs?.length && <p className="muted">Aucun facteur de risque détecté.</p>}
      </Card>}

      {modal === "edit" && <Modal wide title="Modifier le fournisseur" onClose={() => setModal(null)}><SupplierForm edit initial={s} onDone={() => { setModal(null); reload(); }} /></Modal>}
      {modal === "rib" && <Modal title="Nouveau RIB" onClose={() => setModal(null)}>
        <div className="form-grid"><Field label="Banque"><input onChange={set("bank_name")} /></Field><Field label="RIB (20 chiffres)"><input onChange={set("rib")} /></Field>
          <Field label="IBAN"><input onChange={set("iban")} /></Field><Field label="SWIFT"><input onChange={set("swift")} /></Field>
          <Field label="Devise"><select onChange={set("currency")} defaultValue={s.currency}><option>TND</option><option>EUR</option><option>USD</option></select></Field></div>
        <div className="modal-actions"><button className="btn primary" onClick={() => post(`/api/suppliers/${id}/bank-accounts`, { currency: s.currency, ...form }, "RIB enregistré — à vérifier")}>Enregistrer</button></div>
      </Modal>}
      {modal === "contrat" && <Modal title="Nouveau contrat" onClose={() => setModal(null)}>
        <div className="form-grid"><Field label="Référence"><input onChange={set("reference")} /></Field><Field label="Objet"><input onChange={set("subject")} /></Field>
          <Field label="Début"><input type="date" onChange={set("start_date")} /></Field><Field label="Fin"><input type="date" onChange={set("end_date")} /></Field>
          <Field label="Montant récurrent TTC"><input type="number" onChange={set("recurring_amount_ttc")} /></Field>
          <Field label="Périodicité (mois, 0 = aucune)"><input type="number" onChange={set("frequency_months")} /></Field>
          <Field label="Prochaine échéance"><input type="date" onChange={set("next_due_date")} /></Field><Field label="Préavis (jours)"><input type="number" defaultValue={60} onChange={set("notice_days")} /></Field></div>
        <div className="modal-actions"><button className="btn primary" onClick={() => post(`/api/suppliers/${id}/contracts`, Object.fromEntries(Object.entries(form).filter(([, v]) => v !== "")), "Contrat ajouté")}>Enregistrer</button></div>
      </Modal>}
      {modal === "incident" && <Modal title="Incident fournisseur" onClose={() => setModal(null)}>
        <div className="form-grid"><Field label="Date"><input type="date" defaultValue={today()} onChange={set("incident_date")} /></Field>
          <Field label="Type"><select onChange={set("kind")} defaultValue="retard">{["retard", "qualite", "quantite", "prix", "administratif", "autre"].map((k) => <option key={k}>{k}</option>)}</select></Field>
          <Field label="Gravité"><select onChange={set("severity")} defaultValue="moyenne"><option>faible</option><option>moyenne</option><option>grave</option></select></Field></div>
        <Field label="Description"><textarea onChange={set("description")} /></Field>
        <div className="modal-actions"><button className="btn primary" onClick={() => post(`/api/suppliers/${id}/incidents`, { incident_date: today(), kind: "retard", severity: "moyenne", ...form }, "Incident enregistré")}>Enregistrer</button></div>
      </Modal>}
      {modal === "eval" && <Modal title="Évaluation fournisseur (1 = mauvais, 5 = excellent)" onClose={() => setModal(null)}>
        <div className="form-grid"><Field label="Période"><input placeholder="2026-T4" onChange={set("period")} /></Field>
          {[["quality", "Qualité"], ["delivery", "Délais"], ["compliance", "Respect du contrat"], ["strategic_importance", "Importance stratégique"], ["supply_risk", "Risque de rupture (5 = élevé)"]].map(([k, l]) =>
            <Field key={k} label={l}><select defaultValue={3} onChange={set(k)}>{[1, 2, 3, 4, 5].map((n) => <option key={n}>{n}</option>)}</select></Field>)}</div>
        <Field label="Commentaire"><textarea onChange={set("comment")} /></Field>
        <div className="modal-actions"><button className="btn primary" onClick={() => post(`/api/suppliers/${id}/evaluations`,
          { quality: 3, delivery: 3, compliance: 3, strategic_importance: 3, supply_risk: 3, ...Object.fromEntries(Object.entries(form).map(([k, v]) => [k, ["period", "comment"].includes(k) ? v : Number(v)])) }, "Évaluation enregistrée")}>Enregistrer</button></div>
      </Modal>}
    </div>
  );
}

export function Risk() {
  const [rows, , , err] = useLoad(() => api.get("/api/suppliers/analysis/risk"), []);
  const nav = useNavigate();
  return (
    <div>
      <div className="row between"><h2>Analyse des risques fournisseurs</h2><ExportButtons name="risques" /></div>
      <div className="alert info">Score explicable de 0 à 100 : dépendance (part des achats), litiges, incidents, retards de livraison, évaluation, criticité.
        Les seuils de niveau et de dépendance sont paramétrables.</div>
      <Card>{!rows ? <Loading err={err} /> : <DataTable rows={rows} onRow={(r) => nav(`/fournisseurs/${r.supplier_id}`)} cols={[
        { key: "code", label: "Code" }, { key: "fournisseur", label: "Fournisseur" }, { key: "categorie", label: "Catégorie", kind: "badge" },
        { key: "achats_12m", label: "Achats 12 mois", kind: "money" }, { key: "part_achats_pct", label: "Part %", kind: "num" },
        { key: "score", label: "Score", kind: "num" }, { key: "niveau", label: "Niveau", kind: "badge" },
        { key: "facteurs", label: "Facteurs", render: (r) => r.facteurs.join(" · ") || "—" }]} />}</Card>
      <p className="muted">Mis à jour au {dt(today())}.</p>
    </div>
  );
}
