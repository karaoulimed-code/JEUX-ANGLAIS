import { useState } from "react";
import { api } from "../api";
import { today } from "../format";
import { t } from "../i18n";
import { Card, DataTable, ExportButtons, Field, Loading, Modal, useAction, useCan, useLoad } from "../components/ui";

const KINDS = ["prix", "quantite", "qualite", "retour", "retard_livraison", "facture_contestee", "penalite", "autre"];

export default function Disputes() {
  const [status, setStatus] = useState("");
  const [rows, reload, , err] = useLoad(() => api.get(`/api/disputes?status=${status}`), [status]);
  const [sups] = useLoad(() => api.get("/api/suppliers"), []);
  const [edit, setEdit] = useState<any>(null);
  const [create, setCreate] = useState<any>(null);
  const can = useCan();
  const act = useAction();
  return (
    <div>
      <div className="row between"><h2>Avoirs, retours et litiges fournisseurs</h2>
        <div className="row gap"><ExportButtons name="factures-litigieuses" />
          {can("dispute.manage") && <button className="btn primary" onClick={() => setCreate({ kind: "qualite", opened_at: today(), contested_amount: "0" })}>+ Litige</button>}</div></div>
      <div className="alert info">Les montants contestés sont exclus des paiements et classés « conditionnels » dans les prévisions de décaissement.
        Les avoirs se saisissent dans Factures (type « Avoir ») puis s'imputent sur la facture concernée.</div>
      <Card>
        <select value={status} onChange={(e) => setStatus(e.target.value)} style={{ marginBottom: 8 }}><option value="">Tous</option>
          {["ouvert", "en_cours", "resolu", "clos"].map((s) => <option key={s} value={s}>{t(s)}</option>)}</select>
        {!rows ? <Loading err={err} /> : <DataTable rows={rows} onRow={(r) => can("dispute.manage") && setEdit({ ...r })} cols={[
          { key: "number", label: "N°" }, { key: "fournisseur", label: "Fournisseur" }, { key: "facture", label: "Facture", link: (r) => `/factures/${r.invoice_id}` },
          { key: "kind", label: "Motif" }, { key: "contested_amount", label: "Montant contesté", kind: "money", total: true },
          { key: "opened_at", label: "Ouvert le", kind: "date" }, { key: "status", label: "État", kind: "badge" }, { key: "decision", label: "Décision" }]} />}
      </Card>
      {create && <Modal title="Nouveau litige" onClose={() => setCreate(null)}>
        <div className="form-grid">
          <Field label="Fournisseur"><select onChange={(e) => setCreate({ ...create, supplier_id: Number(e.target.value) })}><option value="">—</option>
            {(sups || []).map((s: any) => <option key={s.id} value={s.id}>{s.code} — {s.legal_name}</option>)}</select></Field>
          <Field label="Facture (id, optionnel)"><input onChange={(e) => setCreate({ ...create, invoice_id: e.target.value ? Number(e.target.value) : null })} /></Field>
          <Field label="Motif"><select value={create.kind} onChange={(e) => setCreate({ ...create, kind: e.target.value })}>{KINDS.map((k) => <option key={k}>{k}</option>)}</select></Field>
          <Field label="Montant contesté"><input type="number" value={create.contested_amount} onChange={(e) => setCreate({ ...create, contested_amount: e.target.value })} /></Field>
          {create.kind === "retour" && <Field label="Quantité retournée"><input type="number" onChange={(e) => setCreate({ ...create, returned_quantity: e.target.value })} /></Field>}
          {create.kind === "penalite" && <Field label="Pénalité contractuelle"><input type="number" onChange={(e) => setCreate({ ...create, penalty_amount: e.target.value })} /></Field>}
        </div>
        <Field label="Exposé"><textarea onChange={(e) => setCreate({ ...create, reason: e.target.value })} /></Field>
        <div className="modal-actions"><button className="btn primary" onClick={async () => { if (await act(() => api.post("/api/disputes", create), "Litige ouvert")) { setCreate(null); reload(); } }}>Ouvrir</button></div>
      </Modal>}
      {edit && <Modal title={`Litige ${edit.number}`} onClose={() => setEdit(null)}>
        <p>{edit.reason}</p>
        <div className="form-grid">
          <Field label="État"><select value={edit.status} onChange={(e) => setEdit({ ...edit, status: e.target.value })}>{["ouvert", "en_cours", "resolu", "clos"].map((s) => <option key={s} value={s}>{t(s)}</option>)}</select></Field>
          <Field label="Issue"><select value={edit.outcome || ""} onChange={(e) => setEdit({ ...edit, outcome: e.target.value || null })}><option value="">—</option>
            {["avoir_obtenu", "rejete", "accord_partiel", "paye", "penalite_appliquee"].map((o) => <option key={o}>{o}</option>)}</select></Field>
          <Field label="Montant contesté"><input type="number" value={edit.contested_amount} onChange={(e) => setEdit({ ...edit, contested_amount: e.target.value })} /></Field>
        </div>
        <Field label="Suivi"><textarea value={edit.progress_notes || ""} onChange={(e) => setEdit({ ...edit, progress_notes: e.target.value })} /></Field>
        <Field label="Décision finale (obligatoire pour clore)"><textarea value={edit.decision || ""} onChange={(e) => setEdit({ ...edit, decision: e.target.value })} /></Field>
        <div className="modal-actions"><button className="btn primary" onClick={async () => {
          const body = { status: edit.status, outcome: edit.outcome || null, contested_amount: edit.contested_amount, progress_notes: edit.progress_notes || null, decision: edit.decision || null };
          if (await act(() => api.patch(`/api/disputes/${edit.id}`, body), "Litige mis à jour")) { setEdit(null); reload(); } }}>Enregistrer</button></div>
      </Modal>}
    </div>
  );
}
