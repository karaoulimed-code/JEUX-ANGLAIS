import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { dt, money, today } from "../format";
import { Badge, Card, DataTable, ExportButtons, Field, Loading, Modal, Tabs, useAction, useCan, useLoad, useMe } from "../components/ui";

export type Line = { description: string; item_ref?: string; quantity: string; unit_price: string; tva_rate: string; account_code?: string; order_line_id?: number };
export const newLine = (): Line => ({ description: "", item_ref: "", quantity: "1", unit_price: "0", tva_rate: "19", account_code: "" });

export function LinesEditor({ lines, setLines, poLines }: { lines: Line[]; setLines: (l: Line[]) => void; poLines?: any[] }) {
  const up = (i: number, k: keyof Line, v: any) => setLines(lines.map((l, j) => (j === i ? { ...l, [k]: v } : l)));
  const pick = (i: number, id: string) => {
    const pl = poLines?.find((p) => String(p.id) === id);
    if (!pl) return up(i, "order_line_id", undefined);
    setLines(lines.map((l, j) => j === i ? { ...l, order_line_id: pl.id, description: pl.description, item_ref: pl.item_ref || "",
      quantity: String(Number(pl.qty_received) - Number(pl.qty_invoiced) || pl.quantity), unit_price: String(pl.unit_price), tva_rate: String(Number(pl.tva_rate)),
      account_code: pl.account_code || "" } : l));
  };
  const ht = lines.reduce((s, l) => s + Number(l.quantity || 0) * Number(l.unit_price || 0), 0);
  const tva = lines.reduce((s, l) => s + Number(l.quantity || 0) * Number(l.unit_price || 0) * Number(l.tva_rate || 0) / 100, 0);
  return (
    <div className="table-wrap">
      <table className="lines">
        <thead><tr>{poLines && <th>Ligne BC</th>}<th>Désignation</th><th>Réf.</th><th>Qté</th><th>P.U. HT</th><th>TVA %</th><th>Compte</th><th className="r">Montant HT</th><th></th></tr></thead>
        <tbody>{lines.map((l, i) => (
          <tr key={i}>
            {poLines && <td><select value={l.order_line_id || ""} onChange={(e) => pick(i, e.target.value)}><option value="">—</option>
              {poLines.map((p) => <option key={p.id} value={p.id}>{p.description} (reçu {Number(p.qty_received)} / facturé {Number(p.qty_invoiced)})</option>)}</select></td>}
            <td><input value={l.description} onChange={(e) => up(i, "description", e.target.value)} /></td>
            <td style={{ width: 90 }}><input value={l.item_ref || ""} onChange={(e) => up(i, "item_ref", e.target.value)} /></td>
            <td style={{ width: 80 }}><input type="number" step="0.001" value={l.quantity} onChange={(e) => up(i, "quantity", e.target.value)} /></td>
            <td style={{ width: 110 }}><input type="number" step="0.001" value={l.unit_price} onChange={(e) => up(i, "unit_price", e.target.value)} /></td>
            <td style={{ width: 75 }}><select value={l.tva_rate} onChange={(e) => up(i, "tva_rate", e.target.value)}>{["19", "13", "7", "0"].map((r) => <option key={r}>{r}</option>)}</select></td>
            <td style={{ width: 85 }}><input value={l.account_code || ""} onChange={(e) => up(i, "account_code", e.target.value)} placeholder="6061" /></td>
            <td className="r">{money(Number(l.quantity || 0) * Number(l.unit_price || 0))}</td>
            <td><button className="btn sm ghost" onClick={() => setLines(lines.filter((_, j) => j !== i))} aria-label="Supprimer">✕</button></td>
          </tr>))}</tbody>
        <tfoot><tr><td colSpan={poLines ? 7 : 6}><button className="btn sm" onClick={() => setLines([...lines, newLine()])}>+ Ligne</button></td>
          <td className="r">HT {money(ht)}<br />TVA {money(tva)}</td><td></td></tr></tfoot>
      </table>
    </div>
  );
}

export const cleanLines = (lines: Line[]) => lines.filter((l) => l.description).map((l) => {
  const o: any = { ...l };
  if (!o.item_ref) delete o.item_ref;
  if (!o.account_code) delete o.account_code;
  if (!o.order_line_id) delete o.order_line_id;
  return o;
});

function NewOrder({ onDone, fromRequest }: { onDone: () => void; fromRequest?: any }) {
  const [sups] = useLoad(() => api.get("/api/suppliers?status=actif"), []);
  const [f, setF] = useState<any>({ supplier_id: fromRequest?.suggested_supplier_id || "", order_date: today(), expected_date: "", notes: "" });
  const [lines, setLines] = useState<Line[]>(fromRequest ? fromRequest.lines.map((l: any) => ({ ...newLine(), description: l.description,
    quantity: String(Number(l.quantity)), unit_price: String(Number(l.estimated_unit_price)) })) : [newLine()]);
  const act = useAction();
  const save = async () => {
    const r = await act(() => api.post("/api/purchasing/orders", { ...f, supplier_id: Number(f.supplier_id), expected_date: f.expected_date || null,
      request_id: fromRequest?.id ?? null, lines: cleanLines(lines) }), "Bon de commande créé");
    if (r) onDone();
  };
  return (
    <div>
      <div className="form-grid">
        <Field label="Fournisseur (actif)"><select value={f.supplier_id} onChange={(e) => setF({ ...f, supplier_id: e.target.value })}><option value="">—</option>
          {(sups || []).map((s: any) => <option key={s.id} value={s.id}>{s.code} — {s.legal_name}</option>)}</select></Field>
        <Field label="Date de commande"><input type="date" value={f.order_date} onChange={(e) => setF({ ...f, order_date: e.target.value })} /></Field>
        <Field label="Livraison prévue"><input type="date" value={f.expected_date} onChange={(e) => setF({ ...f, expected_date: e.target.value })} /></Field>
      </div>
      <LinesEditor lines={lines} setLines={setLines} />
      <Field label="Notes"><textarea value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} /></Field>
      <div className="modal-actions"><button className="btn primary" onClick={save}>Enregistrer (brouillon)</button></div>
    </div>
  );
}

function NewRequest({ onDone }: { onDone: () => void }) {
  const [f, setF] = useState<any>({ request_date: today(), department: "", justification: "", needed_by: "" });
  const [lines, setLines] = useState<any[]>([{ description: "", quantity: "1", estimated_unit_price: "0" }]);
  const act = useAction();
  const save = async () => {
    if (await act(() => api.post("/api/purchasing/requests", { ...f, needed_by: f.needed_by || null, lines: lines.filter((l) => l.description) }), "Demande d'achat créée")) onDone();
  };
  return (
    <div>
      <div className="form-grid">
        <Field label="Date"><input type="date" value={f.request_date} onChange={(e) => setF({ ...f, request_date: e.target.value })} /></Field>
        <Field label="Service"><input value={f.department} onChange={(e) => setF({ ...f, department: e.target.value })} /></Field>
        <Field label="Besoin pour le"><input type="date" value={f.needed_by} onChange={(e) => setF({ ...f, needed_by: e.target.value })} /></Field>
      </div>
      <Field label="Justification"><textarea value={f.justification} onChange={(e) => setF({ ...f, justification: e.target.value })} /></Field>
      <table className="lines"><thead><tr><th>Désignation</th><th>Quantité</th><th>Prix estimé</th></tr></thead><tbody>
        {lines.map((l, i) => <tr key={i}>{(["description", "quantity", "estimated_unit_price"] as const).map((k) => <td key={k}>
          <input value={l[k]} onChange={(e) => setLines(lines.map((x, j) => j === i ? { ...x, [k]: e.target.value } : x))} /></td>)}</tr>)}</tbody></table>
      <button className="btn sm" onClick={() => setLines([...lines, { description: "", quantity: "1", estimated_unit_price: "0" }])}>+ Ligne</button>
      <div className="modal-actions"><button className="btn primary" onClick={save}>Enregistrer</button></div>
    </div>
  );
}

export function Purchasing() {
  const [tab, setTab] = useState("bc");
  const [orders, reloadO] = useLoad(() => api.get("/api/purchasing/orders"), []);
  const [reqs, reloadR] = useLoad(() => api.get("/api/purchasing/requests"), []);
  const [comm] = useLoad(() => api.get("/api/purchasing/commitments"), [orders]);
  const [rni] = useLoad(() => api.get("/api/purchasing/received-not-invoiced"), [orders]);
  const [modal, setModal] = useState<any>(null);
  const can = useCan();
  const me = useMe();
  const act = useAction();
  const nav = useNavigate();
  return (
    <div>
      <div className="row between"><h2>Achats et engagements</h2>
        <div className="row gap">
          {can("pr.create") && <button className="btn" onClick={() => setModal({ k: "da" })}>+ Demande d'achat</button>}
          {can("po.create") && <button className="btn primary" onClick={() => setModal({ k: "bc" })}>+ Bon de commande</button>}
        </div></div>
      <Tabs active={tab} onChange={setTab} tabs={[["bc", "Bons de commande"], ["da", "Demandes d'achat"], ["eng", "Engagements non facturés"], ["rni", "Livraisons non facturées"]]} />
      <Card>
        {tab === "bc" && (!orders ? <Loading /> : <DataTable rows={orders} onRow={(r) => nav(`/achats/commandes/${r.id}`)} cols={[
          { key: "number", label: "N°" }, { key: "fournisseur", label: "Fournisseur" }, { key: "order_date", label: "Date", kind: "date" },
          { key: "expected_date", label: "Livraison prévue", kind: "date" }, { key: "total_ttc", label: "TTC", kind: "money", cur: (r) => r.currency },
          { key: "status", label: "Statut", kind: "badge" }]} />)}
        {tab === "da" && (!reqs ? <Loading /> : <DataTable rows={reqs} cols={[
          { key: "number", label: "N°" }, { key: "request_date", label: "Date", kind: "date" }, { key: "department", label: "Service" },
          { key: "justification", label: "Justification" }, { key: "estimated_amount", label: "Estimation HT", kind: "money" },
          { key: "status", label: "Statut", kind: "badge" },
          { key: "a", label: "", render: (r) => <div className="row gap">
            {r.status === "brouillon" && r.requester_id === me.id && <button className="btn sm" onClick={async () => { await act(() => api.post(`/api/purchasing/requests/${r.id}/submit`), "Soumise"); reloadR(); }}>Soumettre</button>}
            {r.status === "soumise" && can("pr.approve") && <>
              <button className="btn sm ok" onClick={async () => { await act(() => api.post(`/api/purchasing/requests/${r.id}/decision`, { approve: true }), "Approuvée"); reloadR(); }}>Approuver</button>
              <button className="btn sm danger" onClick={async () => { await act(() => api.post(`/api/purchasing/requests/${r.id}/decision`, { approve: false, comment: prompt("Motif") }), "Rejetée"); reloadR(); }}>Rejeter</button></>}
            {r.status === "approuvee" && can("po.create") && <button className="btn sm primary" onClick={() => setModal({ k: "bc", from: r })}>Créer le BC</button>}
          </div> }]} />)}
        {tab === "eng" && <>
          <div className="row between"><p className="muted">Engagements financiers connus avant réception des factures.</p><ExportButtons name="engagements" /></div>
          <DataTable rows={comm || []} cols={[{ key: "numero", label: "BC", link: (r) => `/achats/commandes/${r.order_id}` }, { key: "fournisseur", label: "Fournisseur" },
            { key: "livraison_prevue", label: "Livraison prévue", kind: "date" }, { key: "restant_ttc", label: "Restant TTC", kind: "money", cur: (r) => r.devise },
            { key: "restant_ttc_tnd", label: "Restant TTC (TND)", kind: "money", total: true }, { key: "recu_non_facture_ht", label: "Reçu non facturé HT", kind: "money" },
            { key: "statut", label: "Statut", kind: "badge" }]} /></>}
        {tab === "rni" && <DataTable rows={rni || []} cols={[{ key: "numero", label: "BC", link: (r) => `/achats/commandes/${r.order_id}` },
          { key: "fournisseur", label: "Fournisseur" }, { key: "description", label: "Article" }, { key: "qte_non_facturee", label: "Qté non facturée", kind: "num" },
          { key: "montant_ht", label: "Montant HT", kind: "money", total: true }]} />}
      </Card>
      {modal?.k === "bc" && <Modal wide title="Nouveau bon de commande" onClose={() => setModal(null)}><NewOrder fromRequest={modal.from} onDone={() => { setModal(null); reloadO(); reloadR(); }} /></Modal>}
      {modal?.k === "da" && <Modal wide title="Nouvelle demande d'achat" onClose={() => setModal(null)}><NewRequest onDone={() => { setModal(null); reloadR(); setTab("da"); }} /></Modal>}
    </div>
  );
}

export function OrderDetail() {
  const { id } = useParams();
  const [po, reload, , err] = useLoad(() => api.get(`/api/purchasing/orders/${id}`), [id]);
  const [rec, setRec] = useState<any>(null);
  const can = useCan();
  const act = useAction();
  if (!po) return <Loading err={err} />;
  const go = async (url: string, body: any, ok: string) => { if (await act(() => api.post(url, body), ok)) reload(); };
  const open = ["approuvee", "partiellement_recue"].includes(po.status);
  return (
    <div>
      <div className="row between">
        <h2>{po.number} — {po.fournisseur} <Badge v={po.status} />{po.revision > 0 && <span className="muted"> (révision {po.revision})</span>}</h2>
        <div className="row gap">
          {po.status === "brouillon" && can("po.create") && <button className="btn primary" onClick={() => go(`/api/purchasing/orders/${id}/submit`, {}, "Soumis pour approbation")}>Soumettre</button>}
          {po.status === "a_approuver" && can("po.approve") && <>
            <button className="btn ok" onClick={() => go(`/api/purchasing/orders/${id}/decision`, { approve: true }, "Commande approuvée")}>Approuver</button>
            <button className="btn danger" onClick={() => go(`/api/purchasing/orders/${id}/decision`, { approve: false, comment: prompt("Motif") }, "Renvoyée en brouillon")}>Rejeter</button></>}
          {open && can("receipt.create") && <button className="btn primary" onClick={() => setRec({ receipt_date: today(), delivery_note_ref: "",
            lines: po.lines.map((l: any) => ({ order_line_id: l.id, description: l.description, reste: Number(l.quantity) - Number(l.qty_received), qty_received: "", qty_rejected: "0" })) })}>Saisir une réception</button>}
          {open && can("po.create") && <button className="btn" onClick={() => { const r = prompt("Motif de clôture (reliquat non livré)"); r && go(`/api/purchasing/orders/${id}/close`, { reason: r }, "Commande clôturée"); }}>Clôturer</button>}
          {!["annulee", "cloturee", "recue", "partiellement_recue"].includes(po.status) && can("po.approve") &&
            <button className="btn danger" onClick={() => { const r = prompt("Motif d'annulation"); r && go(`/api/purchasing/orders/${id}/cancel`, { reason: r }, "Commande annulée"); }}>Annuler</button>}
        </div>
      </div>
      <Card><dl className="kv"><dt>Date</dt><dd>{dt(po.order_date)}</dd><dt>Livraison prévue</dt><dd>{dt(po.expected_date)}</dd>
        <dt>Conditions de paiement</dt><dd>{po.payment_terms_days} j {po.payment_terms_type}</dd><dt>Devise / cours</dt><dd>{po.currency} / {po.exchange_rate}</dd>
        <dt>Totaux</dt><dd>HT {money(po.total_ht)} · TVA {money(po.total_tva)} · <b>TTC {money(po.total_ttc, po.currency)}</b></dd>
        {po.cancel_reason && <><dt>Motif</dt><dd>{po.cancel_reason}</dd></>}</dl></Card>
      <Card title="Lignes"><DataTable filter={false} rows={po.lines} cols={[{ key: "description", label: "Désignation" }, { key: "item_ref", label: "Réf." },
        { key: "quantity", label: "Commandé", kind: "num" }, { key: "qty_received", label: "Reçu", kind: "num" }, { key: "qty_invoiced", label: "Facturé", kind: "num" },
        { key: "unit_price", label: "P.U.", kind: "money" }, { key: "tva_rate", label: "TVA %", kind: "num" }, { key: "account_code", label: "Compte" }]} /></Card>
      <Card title="Réceptions"><DataTable filter={false} rows={po.receptions} cols={[{ key: "number", label: "N°" }, { key: "receipt_date", label: "Date", kind: "date" },
        { key: "delivery_note_ref", label: "BL" }, { key: "lines", label: "Quantités (reçu / rejeté)", render: (r) => r.lines.map((l: any) => `${Number(l.qty_received)} / ${Number(l.qty_rejected)}`).join(" · ") }]} /></Card>
      {rec && <Modal wide title="Bon de réception" onClose={() => setRec(null)}>
        <div className="form-grid"><Field label="Date de réception"><input type="date" value={rec.receipt_date} onChange={(e) => setRec({ ...rec, receipt_date: e.target.value })} /></Field>
          <Field label="N° bon de livraison"><input value={rec.delivery_note_ref} onChange={(e) => setRec({ ...rec, delivery_note_ref: e.target.value })} /></Field></div>
        <table className="lines"><thead><tr><th>Article</th><th>Reste à recevoir</th><th>Qté reçue</th><th>Dont rejetée (non conforme)</th></tr></thead>
          <tbody>{rec.lines.map((l: any, i: number) => <tr key={i}><td>{l.description}</td><td>{l.reste}</td>
            {(["qty_received", "qty_rejected"] as const).map((k) => <td key={k}><input type="number" value={l[k]} onChange={(e) => setRec({ ...rec, lines: rec.lines.map((x: any, j: number) => j === i ? { ...x, [k]: e.target.value } : x) })} /></td>)}</tr>)}</tbody></table>
        <div className="modal-actions"><button className="btn primary" onClick={async () => {
          const r = await act(() => api.post("/api/purchasing/receipts", { order_id: po.id, receipt_date: rec.receipt_date, delivery_note_ref: rec.delivery_note_ref || null,
            lines: rec.lines.filter((l: any) => Number(l.qty_received) > 0).map((l: any) => ({ order_line_id: l.order_line_id, qty_received: l.qty_received, qty_rejected: l.qty_rejected || 0 })) }), "Réception enregistrée");
          if (r) { setRec(null); reload(); } }}>Valider la réception</button></div>
      </Modal>}
    </div>
  );
}
