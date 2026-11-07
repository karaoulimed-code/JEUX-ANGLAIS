"""Module 2 — Demandes d'achat, bons de commande, réceptions, engagements."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select

from ..models import (GoodsReceipt, GoodsReceiptLine, PurchaseOrder, PurchaseOrderLine,
                      PurchaseRequest, PurchaseRequestLine, Supplier)
from ..money import D, ZERO, pct, r3
from ..security import BusinessError, Ctx
from .common import (check_period_open, ctx_audit, fx_rate, next_number, setting_bool,
                     setting_dec)

OPEN_PO = ("approuvee", "partiellement_recue", "recue")


def _strict(ctx: Ctx) -> bool:
    return setting_bool(ctx.db, ctx.company_id, "separation_stricte")


# ------------------------------------------------------------ Demandes d'achat
def create_request(ctx: Ctx, data: dict) -> PurchaseRequest:
    lines = data.pop("lines", [])
    pr = PurchaseRequest(company_id=ctx.company_id, requester_id=ctx.user.id,
                         number=next_number(ctx.db, ctx.company_id, "DA", data.get("request_date")),
                         **data)
    pr.lines = [PurchaseRequestLine(**l) for l in lines]
    pr.estimated_amount = r3(sum(D(l.quantity) * D(l.estimated_unit_price) for l in pr.lines))
    ctx.db.add(pr)
    ctx.db.flush()
    ctx_audit(ctx, "creation", "demande_achat", pr.id, {"numero": pr.number})
    return pr


def submit_request(ctx: Ctx, pr: PurchaseRequest) -> PurchaseRequest:
    if pr.status != "brouillon":
        raise BusinessError("Seule une demande en brouillon peut être soumise.")
    if not pr.lines:
        raise BusinessError("La demande doit comporter au moins une ligne.")
    pr.status = "soumise"
    ctx_audit(ctx, "soumission", "demande_achat", pr.id)
    return pr


def decide_request(ctx: Ctx, pr: PurchaseRequest, approve: bool, comment: str | None) -> PurchaseRequest:
    if pr.status != "soumise":
        raise BusinessError("La demande n'est pas en attente de validation.")
    if pr.requester_id == ctx.user.id:
        raise BusinessError("Séparation des tâches : le demandeur ne peut pas valider sa propre demande.",
                            code="separation_taches", status=403)
    pr.status = "approuvee" if approve else "rejetee"
    pr.approved_by_id, pr.approved_at, pr.decision_comment = ctx.user.id, datetime.utcnow(), comment
    ctx_audit(ctx, "approbation" if approve else "rejet", "demande_achat", pr.id, {"commentaire": comment})
    return pr


# ------------------------------------------------------------ Bons de commande
def _po_totals(po: PurchaseOrder) -> None:
    ht = tva = ZERO
    for l in po.lines:
        base = r3(D(l.quantity) * D(l.unit_price))
        ht += base
        tva += pct(base, l.tva_rate)
    po.total_ht, po.total_tva, po.total_ttc = r3(ht), r3(tva), r3(ht + tva)


def create_order(ctx: Ctx, data: dict) -> PurchaseOrder:
    lines = data.pop("lines", [])
    sup = ctx.db.get(Supplier, data["supplier_id"])
    if not sup or sup.company_id != ctx.company_id:
        raise BusinessError("Fournisseur introuvable.", status=404)
    if sup.status != "actif":
        raise BusinessError(f"Le fournisseur {sup.code} n'est pas actif (statut : {sup.status}).",
                            code="fournisseur_non_autorise")
    if data.get("request_id"):
        pr = ctx.db.get(PurchaseRequest, data["request_id"])
        if not pr or pr.status != "approuvee":
            raise BusinessError("La demande d'achat liée doit être approuvée.")
    if not lines:
        raise BusinessError("Le bon de commande doit comporter au moins une ligne.")
    data.setdefault("currency", sup.currency)
    data.setdefault("payment_terms_days", sup.payment_terms_days)
    data.setdefault("payment_terms_type", sup.payment_terms_type)
    po = PurchaseOrder(company_id=ctx.company_id, created_by_id=ctx.user.id,
                       number=next_number(ctx.db, ctx.company_id, "BC", data.get("order_date")), **data)
    po.exchange_rate = fx_rate(ctx.db, ctx.company_id, po.currency, po.order_date)
    po.lines = [PurchaseOrderLine(**l) for l in lines]
    for l in po.lines:
        if D(l.quantity) <= 0 or D(l.unit_price) < 0:
            raise BusinessError("Quantités strictement positives et prix positifs exigés.")
    _po_totals(po)
    ctx.db.add(po)
    ctx.db.flush()
    if data.get("request_id"):
        pr.status = "convertie"
    ctx_audit(ctx, "creation", "bon_commande", po.id, {"numero": po.number, "ttc": po.total_ttc})
    return po


def submit_order(ctx: Ctx, po: PurchaseOrder) -> PurchaseOrder:
    if po.status != "brouillon":
        raise BusinessError("Seul un bon de commande en brouillon peut être soumis.")
    po.status = "a_approuver"
    ctx_audit(ctx, "soumission", "bon_commande", po.id)
    return po


def approve_order(ctx: Ctx, po: PurchaseOrder, approve: bool, comment: str | None = None) -> PurchaseOrder:
    if po.status != "a_approuver":
        raise BusinessError("Le bon de commande n'est pas en attente d'approbation.")
    if _strict(ctx):
        if po.created_by_id == ctx.user.id:
            raise BusinessError("Séparation des tâches : l'émetteur du bon de commande ne peut pas l'approuver.",
                                code="separation_taches", status=403)
        if po.request_id:
            pr = ctx.db.get(PurchaseRequest, po.request_id)
            if pr and pr.requester_id == ctx.user.id:
                raise BusinessError("Séparation des tâches : le demandeur de l'achat ne peut pas approuver la commande.",
                                    code="separation_taches", status=403)
    ttc_tnd = r3(D(po.total_ttc) * D(po.exchange_rate))
    if approve and ttc_tnd >= setting_dec(ctx.db, ctx.company_id, "seuil_bc_validation_dg") and ctx.user.role != "dg":
        raise BusinessError(f"Commande de {ttc_tnd} TND : approbation du Directeur général requise.",
                            code="niveau_insuffisant", status=403)
    po.status = "approuvee" if approve else "brouillon"
    if approve:
        po.approved_by_id, po.approved_at = ctx.user.id, datetime.utcnow()
    ctx_audit(ctx, "approbation" if approve else "rejet", "bon_commande", po.id, {"commentaire": comment})
    return po


def modify_order(ctx: Ctx, po: PurchaseOrder, data: dict) -> PurchaseOrder:
    """Modification : possible en brouillon ; après approbation seulement si rien n'est réceptionné
    ni facturé — le BC repasse alors en brouillon et doit être ré-approuvé (révision tracée)."""
    if po.status in ("annulee", "cloturee", "recue", "partiellement_recue"):
        raise BusinessError("Commande non modifiable (réceptionnée, clôturée ou annulée).")
    if any(D(l.qty_received) > 0 or D(l.qty_invoiced) > 0 for l in po.lines):
        raise BusinessError("Commande déjà réceptionnée ou facturée : modification impossible.")
    before = {"ttc": str(po.total_ttc), "revision": po.revision}
    if "lines" in data and data["lines"] is not None:
        po.lines.clear()
        ctx.db.flush()
        po.lines.extend(PurchaseOrderLine(**l) for l in data.pop("lines"))
    for k in ("expected_date", "notes", "payment_terms_days"):
        if data.get(k) is not None:
            setattr(po, k, data[k])
    _po_totals(po)
    if po.status != "brouillon":
        po.status, po.approved_by_id, po.approved_at = "brouillon", None, None
        po.revision += 1
    ctx_audit(ctx, "modification", "bon_commande", po.id, {"avant": before, "ttc_apres": str(po.total_ttc)})
    return po


def cancel_order(ctx: Ctx, po: PurchaseOrder, reason: str) -> PurchaseOrder:
    if any(D(l.qty_received) > 0 for l in po.lines):
        raise BusinessError("Commande partiellement réceptionnée : utilisez la clôture (solde du reliquat).")
    if po.status in ("annulee", "cloturee"):
        raise BusinessError("Commande déjà annulée ou clôturée.")
    po.status, po.cancel_reason = "annulee", reason
    ctx_audit(ctx, "annulation", "bon_commande", po.id, {"motif": reason})
    return po


def close_order(ctx: Ctx, po: PurchaseOrder, reason: str) -> PurchaseOrder:
    if po.status not in OPEN_PO:
        raise BusinessError("Seule une commande approuvée/en cours peut être clôturée.")
    po.status, po.cancel_reason = "cloturee", reason
    ctx_audit(ctx, "cloture", "bon_commande", po.id, {"motif": reason})
    return po


# ------------------------------------------------------------ Réceptions
def create_receipt(ctx: Ctx, data: dict) -> GoodsReceipt:
    po = ctx.db.get(PurchaseOrder, data["order_id"])
    if not po or po.company_id != ctx.company_id:
        raise BusinessError("Bon de commande introuvable.", status=404)
    if po.status not in ("approuvee", "partiellement_recue"):
        raise BusinessError("Réception possible uniquement sur une commande approuvée non soldée.")
    if _strict(ctx) and po.approved_by_id == ctx.user.id:
        raise BusinessError("Séparation des tâches : l'approbateur de la commande ne peut pas réceptionner.",
                            code="separation_taches", status=403)
    check_period_open(ctx.db, ctx.company_id, data["receipt_date"])
    tol = setting_dec(ctx.db, ctx.company_id, "tolerance_qte_pct")
    by_id = {l.id: l for l in po.lines}
    gr = GoodsReceipt(company_id=ctx.company_id, order_id=po.id, received_by_id=ctx.user.id,
                      number=next_number(ctx.db, ctx.company_id, "BR", data["receipt_date"]),
                      receipt_date=data["receipt_date"], delivery_note_ref=data.get("delivery_note_ref"),
                      notes=data.get("notes"))
    for ld in data["lines"]:
        pol = by_id.get(ld["order_line_id"])
        if not pol:
            raise BusinessError("Ligne de commande inconnue pour ce bon de commande.")
        rec, rej = D(ld["qty_received"]), D(ld.get("qty_rejected") or 0)
        if rec <= 0 or rej < 0 or rej > rec:
            raise BusinessError("Quantités de réception invalides.")
        accepted = rec - rej
        max_qty = D(pol.quantity) * (1 + tol / 100)
        if D(pol.qty_received) + accepted > max_qty:
            raise BusinessError(
                f"Ligne « {pol.description} » : réception ({D(pol.qty_received) + accepted}) supérieure à la "
                f"quantité commandée ({pol.quantity}).", code="sur_reception")
        pol.qty_received = r3(D(pol.qty_received) + accepted)
        gr.lines.append(GoodsReceiptLine(order_line_id=pol.id, qty_received=rec, qty_rejected=rej,
                                         comment=ld.get("comment")))
    if not gr.lines:
        raise BusinessError("La réception doit comporter au moins une ligne.")
    po.status = "recue" if all(D(l.qty_received) >= D(l.quantity) for l in po.lines) else "partiellement_recue"
    ctx.db.add(gr)
    ctx.db.flush()
    ctx_audit(ctx, "creation", "reception", gr.id, {"numero": gr.number, "bc": po.number})
    return gr


def commitments(ctx: Ctx, as_of: date | None = None) -> list[dict]:
    """Engagements non encore facturés (commandes approuvées, montant restant TTC)."""
    rows = []
    q = select(PurchaseOrder).where(PurchaseOrder.company_id == ctx.company_id,
                                    PurchaseOrder.status.in_(OPEN_PO))
    for po in ctx.db.scalars(q):
        rem_ht = rem_tva = ZERO
        rec_not_inv = ZERO
        for l in po.lines:
            rq = max(D(l.quantity) - D(l.qty_invoiced), ZERO)
            base = r3(rq * D(l.unit_price))
            rem_ht += base
            rem_tva += pct(base, l.tva_rate)
            rec_not_inv += r3(max(D(l.qty_received) - D(l.qty_invoiced), ZERO) * D(l.unit_price))
        rem = r3(rem_ht + rem_tva)
        if rem <= 0:
            continue
        sup = ctx.db.get(Supplier, po.supplier_id)
        rows.append({
            "order_id": po.id, "numero": po.number, "fournisseur": sup.legal_name, "supplier_id": sup.id,
            "date_commande": po.order_date, "livraison_prevue": po.expected_date, "devise": po.currency,
            "restant_ht": r3(rem_ht), "restant_ttc": rem, "restant_ttc_tnd": r3(rem * D(po.exchange_rate)),
            "recu_non_facture_ht": r3(rec_not_inv), "statut": po.status,
            "delai_paiement": po.payment_terms_days,
        })
    return rows
