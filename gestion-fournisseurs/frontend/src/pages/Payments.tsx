import { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { dt, money, today } from "../format";
import { t } from "../i18n";
import { Badge, Card, DataTable, Field, Kpi, Loading, Modal, Tabs, useAction, useCan, useLoad, useMe } from "../components/ui";

const METHODS = ["virement", "cheque", "effet", "especes", "autre"];

function NewPayment({ onDone, invoiceId }: { onDone: () => void; invoiceId?: string | null }) {
  const [sups] = useLoad(() => api.get("/api/suppliers?status=actif"), []);
  const [accs] = useLoad(() => api.get("/api/treasury/accounts"), []);
  const [f, setF] = useState<any>({ supplier_id: "", kind: "reglement", method: "virement", treasury_account_id: "", payment_date: today(), due_date: "", reference: "", unallocated_amount: "", notes: "" });
  const [invs] = useLoad(() => f.supplier_id ? api.get(`/api/invoices?supplier_id=${f.supplier_id}`).then((r: any[]) => r.filter((i) => i.workflow_status === "validee" && i.doc_type !== "avoir" && i.solde > 0)) : Promise.resolve([]), [f.supplier_id]);
  const [alloc, setAlloc] = useState<Record<number, string>>({});
  const act = useAction();
  useEffect(() => {
    if (invoiceId) api.get(`/api/invoices/${invoiceId}`).then((i) => { setF((x: any) => ({ ...x, supplier_id: String(i.supplier_id) })); setAlloc({ [i.id]: String(i.payable) }); });
  }, [invoiceId]);
  useEffect(() => { if (accs?.length && !f.treasury_account_id) setF((x: any) => ({ ...x, treasury_account_id: String(accs[0].id) })); }, [accs]);
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  const save = async () => {
    const body: any = { ...f, supplier_id: Number(f.supplier_id), treasury_account_id: f.treasury_account_id ? Number(f.treasury_account_id) : null,
      due_date: f.due_date || null, reference: f.reference || null, unallocated_amount: f.unallocated_amount || null, notes: f.notes || null,
      allocations: Object.entries(alloc).filter(([, v]) => Number(v) > 0).map(([k, v]) => ({ invoice_id: Number(k), amount: v })) };
    const r = await act(() => api.post("/api/payments", body), "Règlement préparé (brouillon)");
    if (r) onDone();
  };
  const total = Object.values(alloc).reduce((s, v) => s + Number(v || 0), 0);
  return (
    <div>
      <div className="form-grid">
        <Field label="Fournisseur"><select value={f.supplier_id} onChange={set("supplier_id")}><option value="">—</option>
          {(sups || []).map((s: any) => <option key={s.id} value={s.id}>{s.code} — {s.legal_name}</option>)}</select></Field>
        <Field label="Nature"><select value={f.kind} onChange={set("kind")}><option value="reglement">Règlement de factures</option><option value="avance">Avance fournisseur</option></select></Field>
        <Field label="Moyen de paiement"><select value={f.method} onChange={set("method")}>{METHODS.map((m) => <option key={m}>{m}</option>)}</select></Field>
        <Field label="Compte de trésorerie"><select value={f.treasury_account_id} onChange={set("treasury_account_id")}>{(accs || []).map((a: any) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></Field>
        <Field label="Date prévue"><input type="date" value={f.payment_date} onChange={set("payment_date")} /></Field>
        {f.method === "effet" && <Field label="Échéance de l'effet"><input type="date" value={f.due_date} onChange={set("due_date")} /></Field>}
        <Field label="Référence (n° chèque, effet, ordre)"><input value={f.reference} onChange={set("reference")} /></Field>
        <Field label={f.kind === "avance" ? "Montant de l'avance" : "Montant non affecté (optionnel)"}><input type="number" value={f.unallocated_amount} onChange={set("unallocated_amount")} /></Field>
      </div>
      {f.kind === "reglement" && <Card title="Factures à régler">
        <DataTable filter={false} rows={invs || []} empty="Aucune facture validée à régler." cols={[
          { key: "internal_ref", label: "Réf." }, { key: "supplier_number", label: "N°" }, { key: "due_date", label: "Échéance", kind: "date" },
          { key: "solde", label: "Solde", kind: "money", cur: (r) => r.currency }, { key: "statut", label: "Statut", kind: "badge" },
          { key: "x", label: "Montant à régler (TTC, RS déduite automatiquement)", render: (r) => <input type="number" step="0.001" value={alloc[r.id] ?? ""}
            onChange={(e) => setAlloc({ ...alloc, [r.id]: e.target.value })} onDoubleClick={() => setAlloc({ ...alloc, [r.id]: String(r.solde) })} placeholder="double-clic = solde" /> }]} />
        <div className="r"><b>Total affecté : {money(total)}</b></div>
      </Card>}
      <div className="modal-actions"><button className="btn primary" onClick={save}>Préparer le règlement</button></div>
    </div>
  );
}

function Plan({ onDone }: { onDone: () => void }) {
  const [horizon, setHorizon] = useState(30);
  const [cash, setCash] = useState("");
  const [plan, , , err] = useLoad(() => api.get(`/api/payments/plan?horizon_days=${horizon}${cash ? `&cash_available=${cash}` : ""}`), [horizon, cash]);
  const [sel, setSel] = useState<Set<any>>(new Set());
  const [method, setMethod] = useState("virement");
  const [accs] = useLoad(() => api.get("/api/treasury/accounts"), []);
  const act = useAction();
  useEffect(() => { if (plan) setSel(new Set(plan.propositions.filter((p: any) => p.retenu).map((p: any) => p.invoice_id))); }, [plan]);
  if (!plan) return <Loading err={err} />;
  const chosen = plan.propositions.filter((p: any) => sel.has(p.invoice_id));
  const total = chosen.reduce((s: number, p: any) => s + Number(p.payable_tnd_net_rs), 0);
  return (
    <div>
      <div className="row gap">
        <Field label="Horizon (jours)"><input type="number" value={horizon} onChange={(e) => setHorizon(Number(e.target.value))} /></Field>
        <Field label="Trésorerie mobilisable (TND)" hint={`par défaut : ${money(plan.tresorerie_disponible)}`}><input type="number" value={cash} onChange={(e) => setCash(e.target.value)} /></Field>
        <Field label="Moyen"><select value={method} onChange={(e) => setMethod(e.target.value)}>{METHODS.map((m) => <option key={m}>{m}</option>)}</select></Field>
      </div>
      <div className="grid g4" style={{ margin: "10px 0" }}>
        <Kpi label="Trésorerie retenue" value={money(plan.tresorerie_disponible)} />
        <Kpi label="Sélection (net de RS)" value={money(total)} tone={total > Number(plan.tresorerie_disponible) ? "err" : "ok"} />
        <Kpi label="Solde après paiements" value={money(Number(plan.tresorerie_disponible) - total)} />
        <Kpi label="Coût de financement retenu" value={`${plan.cout_financement_pct} %`} hint="arbitrage des escomptes" />
      </div>
      <div className="alert info">{plan.avertissement}</div>
      <DataTable rows={plan.propositions} selectable={(r) => Number(r.payable) > 0} selected={sel} onSelect={setSel} cols={[
        { key: "ref", label: "Facture" }, { key: "fournisseur", label: "Fournisseur" }, { key: "categorie", label: "Cat.", kind: "badge" },
        { key: "echeance", label: "Échéance", kind: "date" }, { key: "payable", label: "Payable", kind: "money" },
        { key: "payable_tnd_net_rs", label: "Décaissement TND", kind: "money" }, { key: "score", label: "Priorité", kind: "num" },
        { key: "recommandation", label: "Recommandation", render: (r) => <span className={`badge ${r.recommandation.startsWith("payer") ? "ok" : r.recommandation === "report_a_negocier" ? "warn" : "muted"}`}>{r.recommandation.replace(/_/g, " ")}</span> },
        { key: "justification", label: "Justification", render: (r) => <small>{r.justification.join(" ")}</small> }]} />
      <div className="modal-actions"><button className="btn primary" disabled={!chosen.length} onClick={async () => {
        const r = await act(() => api.post("/api/payments/runs", { planned_date: today(), method, treasury_account_id: accs?.[0]?.id ?? null,
          items: chosen.map((p: any) => ({ invoice_id: p.invoice_id, amount: p.payable })) }), "Campagne de paiement créée et soumise à autorisation");
        if (r) onDone(); }}>Créer la campagne de paiement ({chosen.length})</button></div>
    </div>
  );
}

export function Payments() {
  const [sp] = useSearchParams();
  const [tab, setTab] = useState("liste");
  const [status, setStatus] = useState("");
  const [rows, reload, , err] = useLoad(() => api.get(`/api/payments?status=${status}`), [status]);
  const [runs, reloadRuns] = useLoad(() => api.get("/api/payments/runs"), []);
  const [modal, setModal] = useState<string | null>(sp.get("facture") ? "new" : null);
  const can = useCan();
  const act = useAction();
  const nav = useNavigate();
  return (
    <div>
      <div className="row between"><h2>Règlements fournisseurs</h2>
        {can("payment.prepare") && <button className="btn primary" onClick={() => setModal("new")}>+ Préparer un règlement</button>}</div>
      <Tabs active={tab} onChange={setTab} tabs={[["liste", "Règlements"], ...(can("treasury.read") ? [["plan", "Préparation & optimisation"] as [string, string]] : []), ["runs", "Campagnes"]]} />
      {tab === "liste" && <Card>
        <select value={status} onChange={(e) => setStatus(e.target.value)} style={{ marginBottom: 8 }}><option value="">Tous statuts</option>
          {["brouillon", "a_approuver", "approuve", "emis", "debite", "rejete", "annule"].map((s) => <option key={s} value={s}>{t(s)}</option>)}</select>
        {!rows ? <Loading err={err} /> : <DataTable rows={rows} onRow={(r) => nav(`/reglements/${r.id}`)} cols={[
          { key: "number", label: "N°" }, { key: "fournisseur", label: "Fournisseur" }, { key: "kind", label: "Nature" }, { key: "method", label: "Moyen" },
          { key: "reference", label: "Réf." }, { key: "payment_date", label: "Date", kind: "date" }, { key: "cash_amount", label: "Décaissé", kind: "money", cur: (r) => r.currency },
          { key: "rs_amount", label: "Retenue", kind: "money" }, { key: "required_approvals", label: "Signatures" }, { key: "status", label: "Statut", kind: "badge" }]} />}
      </Card>}
      {tab === "plan" && <Card><Plan onDone={() => { reloadRuns(); reload(); setTab("runs"); }} /></Card>}
      {tab === "runs" && <Card>{(runs || []).map((r: any) => <Card key={r.id} title={<>{r.number} — {dt(r.planned_date)} <Badge v={r.status} /></>}
        actions={can("payment.approve") && r.reglements.some((p: any) => p.status === "a_approuver") &&
          <button className="btn ok" onClick={async () => { await act(() => api.post(`/api/payments/runs/${r.id}/approve`), "Campagne autorisée"); reloadRuns(); reload(); }}>Autoriser tous les règlements</button>}>
        <DataTable filter={false} rows={r.reglements} onRow={(p) => nav(`/reglements/${p.id}`)} cols={[{ key: "number", label: "N°" }, { key: "fournisseur", label: "Fournisseur" },
          { key: "cash_amount", label: "Montant", kind: "money", total: true }, { key: "status", label: "Statut", kind: "badge" }]} /></Card>)}
        {runs?.length === 0 && <div className="muted">Aucune campagne.</div>}</Card>}
      {modal === "new" && <Modal wide title="Préparation d'un règlement" onClose={() => setModal(null)}><NewPayment invoiceId={sp.get("facture")} onDone={() => { setModal(null); reload(); }} /></Modal>}
    </div>
  );
}

export function PaymentDetail() {
  const { id } = useParams();
  const [p, reload, , err] = useLoad(() => api.get(`/api/payments/${id}`), [id]);
  const can = useCan();
  const me = useMe();
  const act = useAction();
  const [alloc, setAlloc] = useState<any>(null);
  const [invs] = useLoad(() => p && p.non_affecte > 0 && ["emis", "debite"].includes(p.status) ? api.get(`/api/invoices?supplier_id=${p.supplier_id}`)
    .then((r: any[]) => r.filter((i) => i.workflow_status === "validee" && i.doc_type !== "avoir" && i.solde > 0)) : Promise.resolve([]), [p?.id, p?.status]);
  if (!p) return <Loading err={err} />;
  const go = async (url: string, body: any, ok: string) => { if (await act(() => api.post(url, body), ok)) reload(); };
  return (
    <div>
      <div className="row between">
        <h2>{p.number} — {p.fournisseur} <Badge v={p.status} /></h2>
        <div className="row gap">
          {p.status === "brouillon" && can("payment.prepare") && <button className="btn primary" onClick={() => go(`/api/payments/${id}/submit`, {}, "Soumis à autorisation")}>Soumettre à autorisation</button>}
          {p.status === "a_approuver" && can("payment.approve") && p.prepared_by_id !== me.id && <button className="btn ok" onClick={() => go(`/api/payments/${id}/approve`, {}, "Signature enregistrée")}>Autoriser (signature {p.approved_by_id ? 2 : 1}/{p.required_approvals})</button>}
          {p.status === "approuve" && can("payment.execute") && <button className="btn primary" onClick={() => { const ref = p.reference || prompt("N° de chèque / effet / ordre de virement") || null; go(`/api/payments/${id}/execute`, { reference: ref }, "Décaissement enregistré"); }}>Exécuter le décaissement</button>}
          {["brouillon", "a_approuver", "approuve"].includes(p.status) && can("payment.prepare") && <button className="btn danger" onClick={() => { const r = prompt("Motif d'annulation"); r && go(`/api/payments/${id}/cancel`, { reason: r }, "Règlement annulé"); }}>Annuler</button>}
          {["emis", "debite"].includes(p.status) && can("bank.reconcile") && <button className="btn danger" onClick={() => { const r = prompt("Motif (chèque rejeté, virement retourné, effet impayé)"); r && go(`/api/payments/${id}/reject`, { reason: r }, "Rejet enregistré — dette rétablie"); }}>Rejet bancaire</button>}
          {p.non_affecte > 0 && ["emis", "debite"].includes(p.status) && can("payment.prepare") && <button className="btn" onClick={() => setAlloc({ invoice_id: "", amount: p.non_affecte })}>Affecter le non-affecté</button>}
        </div>
      </div>
      <Card><dl className="kv">
        <dt>Nature / moyen</dt><dd>{p.kind} / {p.method}</dd><dt>Référence</dt><dd>{p.reference || "—"}</dd>
        <dt>Date</dt><dd>{dt(p.payment_date)}{p.due_date && ` (échéance effet ${dt(p.due_date)})`}</dd><dt>Devise / cours</dt><dd>{p.currency} / {p.exchange_rate}</dd>
        <dt>Montant décaissé</dt><dd><b>{money(p.cash_amount, p.currency)}</b></dd><dt>Retenue à la source</dt><dd>{money(p.rs_amount)}</dd>
        <dt>Non affecté</dt><dd>{money(p.non_affecte)}</dd><dt>Signatures requises</dt><dd>{p.required_approvals}</dd>
        {p.cleared_date && <><dt>Débité le</dt><dd>{dt(p.cleared_date)}</dd></>}
        {p.rejection_reason && <><dt>Motif rejet / annulation</dt><dd>{p.rejection_reason}</dd></>}</dl></Card>
      <Card title="Affectation aux factures"><DataTable filter={false} rows={p.allocations} cols={[
        { key: "facture", label: "Facture", link: (r) => `/factures/${r.invoice_id}` }, { key: "numero", label: "N°" }, { key: "allocation_date", label: "Date", kind: "date" },
        { key: "amount", label: "Montant soldé", kind: "money", total: true }, { key: "rs_amount", label: "dont RS", kind: "money", total: true },
        { key: "fx_difference_tnd", label: "Écart de change TND", kind: "money" }, { key: "cancelled", label: "", render: (r) => r.cancelled ? <Badge v="annule" /> : "" }]} /></Card>
      {alloc && <Modal title="Affecter le montant non affecté" onClose={() => setAlloc(null)}>
        <Field label="Facture"><select onChange={(e) => setAlloc({ ...alloc, invoice_id: Number(e.target.value) })}><option value="">—</option>
          {(invs || []).map((i: any) => <option key={i.id} value={i.id}>{i.internal_ref} n°{i.supplier_number} — solde {money(i.solde)}</option>)}</select></Field>
        <Field label="Montant"><input type="number" value={alloc.amount} onChange={(e) => setAlloc({ ...alloc, amount: e.target.value })} /></Field>
        <div className="modal-actions"><button className="btn primary" onClick={async () => { if (await act(() => api.post(`/api/payments/${id}/allocate`, { ...alloc, allocation_date: today() }), "Affectation enregistrée")) { setAlloc(null); reload(); } }}>Affecter</button></div>
      </Modal>}
    </div>
  );
}

export function Treasury() {
  const [accs, reload, , err] = useLoad(() => api.get("/api/treasury/accounts"), []);
  const [sel, setSel] = useState<number | null>(null);
  const [rec, reloadRec] = useLoad(() => sel ? api.get(`/api/treasury/accounts/${sel}/reconciliation`) : Promise.resolve(null), [sel]);
  const [modal, setModal] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [newAcc, setNewAcc] = useState<any>({ name: "", bank_name: "", rib: "", account_code: "532", opening_balance: "0" });
  const can = useCan();
  const act = useAction();
  useEffect(() => { if (accs?.length && !sel) setSel(accs[0].id); }, [accs]);
  const importText = async () => {
    const lines = text.trim().split(/\n/).map((l) => l.split(";")).filter((c) => c.length >= 3).map(([d, label, amount, reference]) => {
      const [dd, mm, yy] = d.trim().split("/");
      return { operation_date: yy ? `${yy}-${mm}-${dd}` : d.trim(), label: label.trim(), amount: amount.trim().replace(/\s/g, "").replace(",", "."), reference: reference?.trim() || null };
    });
    const r = await act(() => api.post("/api/treasury/statements", { treasury_account_id: sel, lines }));
    if (r) { setModal(null); setText(""); reload(); reloadRec(); }
  };
  return (
    <div>
      <div className="row between"><h2>Trésorerie et rapprochement bancaire</h2>
        <div className="row gap">{can("settings.manage") && <button className="btn" onClick={() => setModal("acc")}>+ Compte</button>}
          {can("bank.reconcile") && <button className="btn primary" onClick={() => setModal("rel")}>Importer un relevé</button>}</div></div>
      {!accs ? <Loading err={err} /> : <Card><DataTable filter={false} rows={accs} onRow={(r) => setSel(r.id)} cols={[
        { key: "name", label: "Compte" }, { key: "bank_name", label: "Banque" }, { key: "account_code", label: "Compte comptable" },
        { key: "solde_releve", label: "Solde relevé", kind: "money", total: true }, { key: "paiements_emis_non_debites", label: "Émis non débités", kind: "money", total: true },
        { key: "solde_disponible_previsionnel", label: "Disponible prévisionnel", kind: "money", total: true }]} /></Card>}
      {rec && <div className="grid g2">
        <Card title={`Chèques / virements émis non présentés — ${rec.compte}`}><DataTable rows={rec.emis_non_presentes} empty="Aucun." cols={[
          { key: "numero", label: "N°", link: (r) => `/reglements/${r.id}` }, { key: "moyen", label: "Moyen" }, { key: "reference", label: "Réf." },
          { key: "date", label: "Date", kind: "date" }, { key: "montant_tnd", label: "Montant", kind: "money", total: true }, { key: "anciennete_jours", label: "Ancienneté (j)" }]} /></Card>
        <Card title="Lignes de relevé non rapprochées (débits)"><DataTable rows={rec.lignes_non_rapprochees} empty="Aucune." cols={[
          { key: "date", label: "Date", kind: "date" }, { key: "libelle", label: "Libellé" }, { key: "reference", label: "Réf." }, { key: "montant", label: "Montant", kind: "money" },
          { key: "x", label: "", render: (r) => can("bank.reconcile") && rec.emis_non_presentes.length > 0 ? <select defaultValue="" onChange={async (e) => {
            if (!e.target.value) return;
            if (await act(() => api.post("/api/treasury/match", { statement_line_id: r.id, payment_id: Number(e.target.value) }), "Rapproché")) { reload(); reloadRec(); } }}>
            <option value="">Rapprocher avec…</option>{rec.emis_non_presentes.map((p: any) => <option key={p.id} value={p.id}>{p.numero} {money(p.montant_tnd)}</option>)}</select> : null }]} /></Card>
      </div>}
      {modal === "rel" && <Modal title="Import de relevé bancaire" onClose={() => setModal(null)}>
        <p className="muted">Une opération par ligne : <code>JJ/MM/AAAA;libellé;montant;référence</code> (débit en négatif). Le rapprochement automatique compare montant et référence.</p>
        <textarea rows={8} style={{ width: "100%" }} value={text} onChange={(e) => setText(e.target.value)} placeholder="05/11/2026;CHQ 4471001 ALPHA;-11246,500;CHQ-4471001" />
        <div className="modal-actions"><button className="btn primary" onClick={importText}>Importer</button></div>
      </Modal>}
      {modal === "acc" && <Modal title="Nouveau compte de trésorerie" onClose={() => setModal(null)}>
        <div className="form-grid">{[["name", "Nom"], ["bank_name", "Banque"], ["rib", "RIB"], ["account_code", "Compte comptable"], ["opening_balance", "Solde d'ouverture"]].map(([k, l]) =>
          <Field key={k} label={l}><input value={newAcc[k]} onChange={(e) => setNewAcc({ ...newAcc, [k]: e.target.value })} /></Field>)}
          <Field label="Date d'ouverture"><input type="date" onChange={(e) => setNewAcc({ ...newAcc, opening_date: e.target.value })} /></Field></div>
        <div className="modal-actions"><button className="btn primary" onClick={async () => { if (await act(() => api.post("/api/treasury/accounts", newAcc), "Compte créé")) { setModal(null); reload(); } }}>Créer</button></div>
      </Modal>}
    </div>
  );
}
