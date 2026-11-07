import { useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, download } from "../api";
import { dt, dtime, money, today } from "../format";
import { t } from "../i18n";
import { Badge, Card, DataTable, Field, Loading, Modal, useAction, useCan, useLoad } from "../components/ui";
import { cleanLines, Line, LinesEditor, newLine } from "./Purchasing";

const STATUTS = ["brouillon", "en_attente_validation", "validee", "non_echue", "echue", "partiellement_reglee", "reglee", "en_litige", "annulee"];

function InvoiceForm({ onDone, initial }: { onDone: (id: number) => void; initial?: any }) {
  const [sups] = useLoad(() => api.get("/api/suppliers"), []);
  const [f, setF] = useState<any>(initial ? {
    doc_type: initial.doc_type, supplier_id: initial.supplier_id, supplier_number: initial.supplier_number, invoice_date: initial.invoice_date,
    reception_date: initial.reception_date || "", order_id: initial.order_id || "", currency: initial.currency, exchange_rate: initial.exchange_rate,
    stamp_duty: initial.stamp_duty, other_taxes: initial.other_taxes, declared_total_ttc: initial.declared_total_ttc ?? "", due_date: "", description: initial.description || "",
    origin_invoice_id: initial.origin_invoice_id || "" } :
    { doc_type: "facture", supplier_id: "", supplier_number: "", invoice_date: today(), reception_date: today(), order_id: "", currency: "",
      exchange_rate: "", stamp_duty: "", other_taxes: "", declared_total_ttc: "", due_date: "", description: "", origin_invoice_id: "" });
  const [lines, setLines] = useState<Line[]>(initial ? initial.lines.map((l: any) => ({ description: l.description, item_ref: l.item_ref || "",
    quantity: String(l.quantity), unit_price: String(l.unit_price), tva_rate: String(Number(l.tva_rate)), account_code: l.account_code || "", order_line_id: l.order_line_id })) : [newLine()]);
  const [orders] = useLoad(() => f.supplier_id ? api.get(`/api/purchasing/orders?supplier_id=${f.supplier_id}`) : Promise.resolve([]), [f.supplier_id]);
  const po = orders?.find((o: any) => String(o.id) === String(f.order_id));
  const act = useAction();
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  const save = async () => {
    const body: any = { ...f, lines: cleanLines(lines) };
    for (const k of ["order_id", "supplier_id", "origin_invoice_id"]) body[k] = body[k] ? Number(body[k]) : null;
    for (const k of ["reception_date", "exchange_rate", "stamp_duty", "other_taxes", "declared_total_ttc", "due_date", "currency", "description"]) if (body[k] === "") body[k] = null;
    if (initial) { delete body.doc_type; delete body.supplier_id; delete body.currency; }
    const r = await act(() => initial ? api.patch(`/api/invoices/${initial.id}`, body) : api.post("/api/invoices", body), "Facture enregistrée en brouillon");
    if (r) onDone(r.id);
  };
  return (
    <div>
      <div className="form-grid">
        <Field label="Type"><select value={f.doc_type} onChange={set("doc_type")} disabled={!!initial}><option value="facture">Facture</option><option value="avoir">Avoir</option><option value="acompte">Facture d'acompte</option></select></Field>
        <Field label="Fournisseur"><select value={f.supplier_id} onChange={set("supplier_id")} disabled={!!initial}><option value="">—</option>
          {(sups || []).map((s: any) => <option key={s.id} value={s.id}>{s.code} — {s.legal_name}</option>)}</select></Field>
        <Field label="N° de facture fournisseur"><input value={f.supplier_number} onChange={set("supplier_number")} /></Field>
        <Field label="Date de facture"><input type="date" value={f.invoice_date} onChange={set("invoice_date")} /></Field>
        <Field label="Date de réception"><input type="date" value={f.reception_date} onChange={set("reception_date")} /></Field>
        {f.doc_type !== "avoir" && <Field label="Bon de commande"><select value={f.order_id} onChange={set("order_id")}><option value="">Sans BC</option>
          {(orders || []).filter((o: any) => ["approuvee", "partiellement_recue", "recue", "cloturee"].includes(o.status)).map((o: any) => <option key={o.id} value={o.id}>{o.number} ({money(o.total_ttc)})</option>)}</select></Field>}
        {f.doc_type === "avoir" && <Field label="Facture d'origine (id)"><input value={f.origin_invoice_id} onChange={set("origin_invoice_id")} /></Field>}
        <Field label="Taux de change" hint="vide = cours BCT saisi à la date"><input value={f.exchange_rate ?? ""} onChange={set("exchange_rate")} /></Field>
        <Field label="Droit de timbre" hint="vide = montant paramétré"><input value={f.stamp_duty ?? ""} onChange={set("stamp_duty")} /></Field>
        <Field label="Autres taxes (FODEC…)"><input value={f.other_taxes ?? ""} onChange={set("other_taxes")} /></Field>
        <Field label="Total TTC figurant sur la facture" hint="contrôle de calcul"><input value={f.declared_total_ttc ?? ""} onChange={set("declared_total_ttc")} /></Field>
        <Field label="Échéance" hint="vide = conditions du fournisseur"><input type="date" value={f.due_date} onChange={set("due_date")} /></Field>
      </div>
      <Field label="Objet"><input value={f.description} onChange={set("description")} /></Field>
      <h4>Lignes {po && <span className="muted">— rapprochement avec {po.number}</span>}</h4>
      <LinesEditor lines={lines} setLines={setLines} poLines={po?.lines} />
      <div className="modal-actions"><button className="btn primary" onClick={save}>Enregistrer</button></div>
    </div>
  );
}

function ImportModal({ onDone }: { onDone: () => void }) {
  const [res, setRes] = useState<any>(null);
  const act = useAction();
  return (
    <div>
      <p>Fichier Excel (.xlsx) ou CSV (séparateur « ; »), une facture par ligne. Colonnes : fournisseur (code ou matricule), numero, date_facture,
        date_reception, montant_ht, taux_tva, montant_tva, timbre, devise, taux_change, echeance, description, type.</p>
      <button className="btn sm" onClick={() => act(() => download("/api/invoices/import/template"))}>Télécharger le modèle</button>
      <p><input type="file" accept=".csv,.xlsx" onChange={async (e) => {
        const file = e.target.files?.[0]; if (!file) return;
        const fd = new FormData(); fd.append("file", file);
        const r = await act(() => api.upload("/api/invoices/import", fd));
        if (r) setRes(r);
      }} /></p>
      {res && <div>
        <div className="alert ok">{res.creees.length} facture(s) créée(s) en brouillon — elles restent soumises aux contrôles et à la validation.</div>
        {res.erreurs.length > 0 && <div className="alert err">{res.erreurs.map((e: any) => `Ligne ${e.ligne} : ${e.erreur}`).join(" · ")}</div>}
        <div className="modal-actions"><button className="btn primary" onClick={onDone}>Fermer</button></div></div>}
    </div>
  );
}

export function Invoices() {
  const [sp] = useSearchParams();
  const [statut, setStatut] = useState(sp.get("statut") || "");
  const [doc, setDoc] = useState("");
  const [rows, reload, , err] = useLoad(() => api.get(`/api/invoices?statut=${statut}&doc_type=${doc}`), [statut, doc]);
  const [modal, setModal] = useState<string | null>(null);
  const can = useCan();
  const nav = useNavigate();
  return (
    <div>
      <div className="row between"><h2>Factures fournisseurs</h2>
        {can("invoice.create") && <div className="row gap"><button className="btn" onClick={() => setModal("import")}>Importer Excel / CSV</button>
          <button className="btn primary" onClick={() => setModal("new")}>+ Saisir une facture</button></div>}</div>
      <Card>
        <div className="row gap" style={{ marginBottom: 8 }}>
          <select value={statut} onChange={(e) => setStatut(e.target.value)}><option value="">Tous statuts</option>{STATUTS.map((s) => <option key={s} value={s}>{t(s)}</option>)}</select>
          <select value={doc} onChange={(e) => setDoc(e.target.value)}><option value="">Factures, avoirs, acomptes</option><option value="facture">Factures</option><option value="avoir">Avoirs</option><option value="acompte">Acomptes</option></select>
        </div>
        {!rows ? <Loading err={err} /> : <DataTable rows={rows} onRow={(r) => nav(`/factures/${r.id}`)} cols={[
          { key: "internal_ref", label: "Réf." }, { key: "doc_type", label: "Type" }, { key: "fournisseur", label: "Fournisseur" },
          { key: "supplier_number", label: "N° fournisseur" }, { key: "invoice_date", label: "Date", kind: "date" }, { key: "due_date", label: "Échéance", kind: "date" },
          { key: "total_ttc", label: "TTC", kind: "money", cur: (r) => r.currency }, { key: "solde", label: "Solde", kind: "money" },
          { key: "matching_status", label: "Contrôle", kind: "badge" },
          { key: "nb_anomalies_bloquantes", label: "Anom.", render: (r) => r.nb_anomalies_bloquantes ? <span className="badge err">{r.nb_anomalies_bloquantes}</span> : "" },
          { key: "statut", label: "Statut", kind: "badge" }]} />}
      </Card>
      {modal === "new" && <Modal wide title="Saisie d'une facture fournisseur" onClose={() => setModal(null)}><InvoiceForm onDone={(id) => { setModal(null); nav(`/factures/${id}`); }} /></Modal>}
      {modal === "import" && <Modal title="Import de factures" onClose={() => setModal(null)}><ImportModal onDone={() => { setModal(null); reload(); }} /></Modal>}
    </div>
  );
}

export function InvoiceDetail() {
  const { id } = useParams();
  const [inv, reload, , err] = useLoad(() => api.get(`/api/invoices/${id}`), [id]);
  const [modal, setModal] = useState<string | null>(null);
  const [form, setForm] = useState<any>({});
  const can = useCan();
  const act = useAction();
  const nav = useNavigate();
  const [credits] = useLoad(() => inv && inv.doc_type === "facture" && inv.workflow_status === "validee"
    ? api.get(`/api/invoices?supplier_id=${inv.supplier_id}`).then((r: any[]) => r.filter((x) => ["avoir", "acompte"].includes(x.doc_type) && x.workflow_status === "validee"))
    : Promise.resolve([]), [inv?.id, inv?.workflow_status]);
  if (!inv) return <Loading err={err} />;
  const post = async (url: string, body: any, ok: string) => { if (await act(() => api.post(url, body), ok)) { setModal(null); setForm({}); reload(); } };
  const blocking = (inv.anomalies || []).filter((a: any) => a.gravite === "bloquante");
  return (
    <div>
      <div className="row between">
        <h2>{inv.internal_ref} — {inv.fournisseur} <Badge v={inv.statut} /> <Badge v={inv.matching_status} /></h2>
        <div className="row gap">
          {inv.workflow_status === "brouillon" && can("invoice.create") && <>
            <button className="btn" onClick={() => setModal("edit")}>Modifier</button>
            <button className="btn primary" onClick={() => post(`/api/invoices/${id}/submit`, {}, "Soumise à validation")}>Soumettre à validation</button></>}
          {inv.workflow_status === "en_attente_validation" && can("invoice.validate") && <>
            <button className="btn ok" onClick={() => post(`/api/invoices/${id}/approve`, {}, "Niveau de validation enregistré")}>Valider (niveau {inv.approved_levels + 1}/{inv.required_levels})</button>
            {blocking.length > 0 && !inv.forced && can("invoice.force") && <button className="btn danger" onClick={() => setModal("force")}>Forcer (dérogation DAF)</button>}
            <button className="btn danger" onClick={() => { const r = prompt("Motif du rejet"); r && post(`/api/invoices/${id}/reject`, { reason: r }, "Facture renvoyée en brouillon"); }}>Rejeter</button></>}
          {inv.workflow_status === "validee" && inv.payable > 0 && can("payment.prepare") &&
            <button className="btn primary" onClick={() => nav(`/reglements?facture=${inv.id}`)}>Préparer le règlement</button>}
          {inv.workflow_status === "validee" && can("dispute.manage") && <button className="btn" onClick={() => setModal("litige")}>Ouvrir un litige</button>}
          {inv.workflow_status === "validee" && inv.doc_type === "facture" && can("invoice.validate") && (credits || []).length > 0 &&
            <button className="btn" onClick={() => setModal("credit")}>Imputer un avoir / acompte</button>}
          {inv.workflow_status !== "annulee" && (can("invoice.create") || can("invoice.cancel")) &&
            <button className="btn danger" onClick={() => { const r = prompt("Motif d'annulation (une facture réglée se corrige par avoir)"); r && post(`/api/invoices/${id}/cancel`, { reason: r }, "Facture annulée"); }}>Annuler</button>}
        </div>
      </div>
      <div className="grid g2">
        <Card title="Facture"><dl className="kv">
          <dt>Type</dt><dd>{inv.doc_type}</dd><dt>N° fournisseur</dt><dd>{inv.supplier_number}</dd>
          <dt>Date / réception</dt><dd>{dt(inv.invoice_date)} / {dt(inv.reception_date)}</dd><dt>Échéance</dt><dd>{dt(inv.due_date)}</dd>
          <dt>Bon de commande</dt><dd>{inv.order_id ? <a href={`/achats/commandes/${inv.order_id}`}>BC #{inv.order_id}</a> : "—"}</dd>
          <dt>Devise / cours</dt><dd>{inv.currency} / {inv.exchange_rate}</dd><dt>Source</dt><dd>{inv.source}</dd>
          {inv.cancel_reason && <><dt>Motif d'annulation</dt><dd>{inv.cancel_reason}</dd></>}
          {inv.forced && <><dt>Dérogation</dt><dd className="badge err">{inv.force_justification}</dd></>}
        </dl></Card>
        <Card title="Montants"><dl className="kv">
          <dt>Total HT</dt><dd className="r">{money(inv.total_ht, inv.currency)}</dd><dt>TVA</dt><dd className="r">{money(inv.total_tva)}</dd>
          <dt>Droit de timbre</dt><dd className="r">{money(inv.stamp_duty)}</dd><dt>Autres taxes</dt><dd className="r">{money(inv.other_taxes)}</dd>
          <dt><b>Total TTC</b></dt><dd className="r"><b>{money(inv.total_ttc, inv.currency)}</b></dd>
          <dt>Retenue à la source {inv.rs_code ? `(${inv.rs_code}, ${Number(inv.rs_rate)} %)` : ""}</dt><dd className="r">− {money(inv.rs_amount)}</dd>
          <dt>Net à payer</dt><dd className="r">{money(inv.net_to_pay)}</dd><dt>Contre-valeur TTC</dt><dd className="r">{money(inv.total_ttc_tnd, "TND")}</dd>
          <dt>Montant réglé / imputé</dt><dd className="r">{money(inv.montant_regle)}</dd><dt><b>Solde restant dû</b></dt><dd className="r"><b>{money(inv.solde)}</b></dd>
          {inv.montant_conteste > 0 && <><dt>Dont contesté</dt><dd className="r">{money(inv.montant_conteste)}</dd></>}
          {inv.credit_disponible !== null && inv.credit_disponible !== undefined && <><dt>Crédit disponible</dt><dd className="r">{money(inv.credit_disponible)}</dd></>}
        </dl></Card>
      </div>
      <Card title="Contrôles automatiques (rapprochement commande / réception / facture)" actions={["brouillon", "en_attente_validation"].includes(inv.workflow_status) &&
        <button className="btn sm" onClick={() => post(`/api/invoices/${id}/controls`, {}, "Contrôles relancés")}>Relancer les contrôles</button>}>
        {(inv.anomalies || []).length === 0 ? <div className="alert ok">Aucune anomalie détectée.</div> :
          <ul className="anom">{inv.anomalies.map((a: any, i: number) => <li key={i} className={a.gravite}><b>{a.code}</b>{a.ligne ? ` (ligne ${a.ligne})` : ""} — {a.message}</li>)}</ul>}
      </Card>
      <Card title="Lignes"><DataTable filter={false} rows={inv.lines} cols={[{ key: "description", label: "Désignation" }, { key: "item_ref", label: "Réf." },
        { key: "order_line_id", label: "Ligne BC" }, { key: "quantity", label: "Qté", kind: "num" }, { key: "unit_price", label: "P.U.", kind: "money" },
        { key: "tva_rate", label: "TVA %", kind: "num" }, { key: "amount_ht", label: "HT", kind: "money", total: true }, { key: "amount_tva", label: "TVA", kind: "money", total: true },
        { key: "account_code", label: "Compte" }]} /></Card>
      <div className="grid g2">
        <Card title="Pièces justificatives" actions={<label className="btn sm">Joindre<input type="file" hidden accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff,.xlsx,.docx,.csv" onChange={async (e) => {
          const file = e.target.files?.[0]; if (!file) return;
          const fd = new FormData(); fd.append("entity", "facture"); fd.append("entity_id", String(inv.id)); fd.append("file", file);
          if (await act(() => api.upload("/api/attachments", fd), "Pièce jointe enregistrée")) reload(); }} /></label>}>
          {inv.pieces.length === 0 ? <div className="muted">Aucune pièce.</div> : inv.pieces.map((p: any) =>
            <div key={p.id}><button className="btn sm ghost" onClick={() => act(() => download(`/api/attachments/${p.id}`))}>📎 {p.filename}</button> <span className="muted">{dtime(p.created_at)}</span></div>)}
        </Card>
        <Card title="Circuit de validation">
          {inv.approbations.length === 0 ? <div className="muted">Aucune décision.</div> : <DataTable filter={false} rows={inv.approbations} cols={[
            { key: "level", label: "Niveau" }, { key: "decision", label: "Décision" }, { key: "user_id", label: "Utilisateur #" },
            { key: "comment", label: "Commentaire" }, { key: "created_at", label: "Date", render: (r) => dtime(r.created_at) }]} />}
        </Card>
        <Card title="Règlements affectés"><DataTable filter={false} rows={inv.affectations} empty="Aucun règlement." cols={[
          { key: "paiement", label: "Règlement", link: (r) => `/reglements/${r.payment_id}` }, { key: "moyen", label: "Moyen" },
          { key: "allocation_date", label: "Date", kind: "date" }, { key: "amount", label: "Montant soldé", kind: "money" }, { key: "rs_amount", label: "dont RS", kind: "money" },
          { key: "statut_paiement", label: "Statut", kind: "badge" }]} /></Card>
        <Card title="Litiges et imputations">
          <DataTable filter={false} rows={inv.litiges} empty="Aucun litige." cols={[{ key: "number", label: "Litige" }, { key: "kind", label: "Motif" },
            { key: "contested_amount", label: "Contesté", kind: "money" }, { key: "status", label: "Statut", kind: "badge" }]} />
          <DataTable filter={false} rows={inv.imputations} empty="Aucune imputation d'avoir ou d'acompte." cols={[{ key: "kind", label: "Type" },
            { key: "source_invoice_id", label: "Source #" }, { key: "target_invoice_id", label: "Cible #" }, { key: "amount", label: "Montant", kind: "money" },
            { key: "allocation_date", label: "Date", kind: "date" }]} />
        </Card>
      </div>
      {modal === "edit" && <Modal wide title="Modifier la facture (brouillon)" onClose={() => setModal(null)}><InvoiceForm initial={inv} onDone={() => { setModal(null); reload(); }} /></Modal>}
      {modal === "force" && <Modal title="Validation par dérogation" onClose={() => setModal(null)}>
        <div className="alert warn">Vous validez malgré {blocking.length} anomalie(s) bloquante(s). La justification est conservée au journal d'audit.</div>
        <Field label="Justification détaillée (obligatoire)"><textarea rows={4} onChange={(e) => setForm({ justification: e.target.value })} /></Field>
        <div className="modal-actions"><button className="btn danger" onClick={() => post(`/api/invoices/${id}/approve`, { force: true, justification: form.justification }, "Validation forcée enregistrée")}>Confirmer la dérogation</button></div>
      </Modal>}
      {modal === "litige" && <Modal title="Ouvrir un litige" onClose={() => setModal(null)}>
        <div className="form-grid"><Field label="Motif"><select defaultValue="prix" onChange={(e) => setForm({ ...form, kind: e.target.value })}>
          {["prix", "quantite", "qualite", "retour", "retard_livraison", "facture_contestee", "penalite", "autre"].map((k) => <option key={k}>{k}</option>)}</select></Field>
          <Field label="Montant contesté (devise facture)"><input type="number" onChange={(e) => setForm({ ...form, contested_amount: e.target.value })} /></Field></div>
        <Field label="Exposé du litige"><textarea onChange={(e) => setForm({ ...form, reason: e.target.value })} /></Field>
        <div className="modal-actions"><button className="btn primary" onClick={() => post("/api/disputes", { kind: "prix", ...form, supplier_id: inv.supplier_id, invoice_id: inv.id, opened_at: today() }, "Litige ouvert")}>Ouvrir</button></div>
      </Modal>}
      {modal === "credit" && <Modal title="Imputer un avoir ou un acompte" onClose={() => setModal(null)}>
        <Field label="Document"><select onChange={(e) => setForm({ ...form, source_invoice_id: Number(e.target.value) })}><option value="">—</option>
          {(credits || []).map((c: any) => <option key={c.id} value={c.id}>{c.internal_ref} {c.doc_type} n°{c.supplier_number} — solde {money(c.solde)}</option>)}</select></Field>
        <Field label="Montant TTC à imputer"><input type="number" onChange={(e) => setForm({ ...form, amount: e.target.value })} /></Field>
        <div className="modal-actions"><button className="btn primary" onClick={() => post("/api/invoices/credit-allocations", { ...form, target_invoice_id: inv.id, allocation_date: today() }, "Imputation enregistrée")}>Imputer</button></div>
      </Modal>}
    </div>
  );
}
