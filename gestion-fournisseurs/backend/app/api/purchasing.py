from fastapi import APIRouter, Depends
from sqlalchemy import select

from ..models import (GoodsReceipt, PurchaseOrder, PurchaseOrderLine, PurchaseRequest, Supplier)
from ..money import D, r3
from ..schemas import DecisionIn, GRIn, POIn, POUpdate, PRIn, ReasonIn, ser
from ..security import Ctx, need
from ..services import purchasing as svc
from .deps import file_response, get_or_404

router = APIRouter(prefix="/api/purchasing", tags=["Module 2 - Achats et engagements"])


def _po(ctx, po: PurchaseOrder) -> dict:
    sup = ctx.db.get(Supplier, po.supplier_id)
    return ser(po, fournisseur=sup.legal_name, lines=[ser(l) for l in po.lines],
               receptions=[ser(r, lines=[ser(l) for l in r.lines]) for r in ctx.db.scalars(
                   select(GoodsReceipt).where(GoodsReceipt.order_id == po.id))])


# ---- demandes d'achat
@router.get("/requests")
def list_requests(status: str | None = None, ctx: Ctx = Depends(need("read"))):
    q = select(PurchaseRequest).where(PurchaseRequest.company_id == ctx.company_id)
    if status:
        q = q.where(PurchaseRequest.status == status)
    return [ser(r, lines=[ser(l) for l in r.lines]) for r in ctx.db.scalars(q.order_by(PurchaseRequest.id.desc()))]


@router.post("/requests")
def create_request(body: PRIn, ctx: Ctx = Depends(need("pr.create"))):
    pr = svc.create_request(ctx, body.model_dump())
    ctx.db.commit()
    return ser(pr, lines=[ser(l) for l in pr.lines])


@router.post("/requests/{rid}/submit")
def submit_request(rid: int, ctx: Ctx = Depends(need("pr.create"))):
    pr = svc.submit_request(ctx, get_or_404(ctx, PurchaseRequest, rid, "Demande"))
    ctx.db.commit()
    return ser(pr)


@router.post("/requests/{rid}/decision")
def decide_request(rid: int, body: DecisionIn, ctx: Ctx = Depends(need("pr.approve"))):
    pr = svc.decide_request(ctx, get_or_404(ctx, PurchaseRequest, rid, "Demande"), body.approve, body.comment)
    ctx.db.commit()
    return ser(pr)


# ---- bons de commande
@router.get("/orders")
def list_orders(status: str | None = None, supplier_id: int | None = None, ctx: Ctx = Depends(need("read"))):
    q = select(PurchaseOrder).where(PurchaseOrder.company_id == ctx.company_id)
    if status:
        q = q.where(PurchaseOrder.status == status)
    if supplier_id:
        q = q.where(PurchaseOrder.supplier_id == supplier_id)
    return [_po(ctx, p) for p in ctx.db.scalars(q.order_by(PurchaseOrder.id.desc()))]


@router.get("/orders/{oid}")
def get_order(oid: int, ctx: Ctx = Depends(need("read"))):
    return _po(ctx, get_or_404(ctx, PurchaseOrder, oid, "Commande"))


@router.post("/orders")
def create_order(body: POIn, ctx: Ctx = Depends(need("po.create"))):
    data = body.model_dump()
    for k in ("currency", "payment_terms_days", "payment_terms_type"):
        if data.get(k) is None:
            data.pop(k)
    po = svc.create_order(ctx, data)
    ctx.db.commit()
    return _po(ctx, po)


@router.patch("/orders/{oid}")
def modify_order(oid: int, body: POUpdate, ctx: Ctx = Depends(need("po.create"))):
    po = svc.modify_order(ctx, get_or_404(ctx, PurchaseOrder, oid, "Commande"), body.model_dump(exclude_unset=True))
    ctx.db.commit()
    return _po(ctx, po)


@router.post("/orders/{oid}/submit")
def submit_order(oid: int, ctx: Ctx = Depends(need("po.create"))):
    po = svc.submit_order(ctx, get_or_404(ctx, PurchaseOrder, oid, "Commande"))
    ctx.db.commit()
    return _po(ctx, po)


@router.post("/orders/{oid}/decision")
def approve_order(oid: int, body: DecisionIn, ctx: Ctx = Depends(need("po.approve"))):
    po = svc.approve_order(ctx, get_or_404(ctx, PurchaseOrder, oid, "Commande"), body.approve, body.comment)
    ctx.db.commit()
    return _po(ctx, po)


@router.post("/orders/{oid}/cancel")
def cancel_order(oid: int, body: ReasonIn, ctx: Ctx = Depends(need("po.approve"))):
    po = svc.cancel_order(ctx, get_or_404(ctx, PurchaseOrder, oid, "Commande"), body.reason)
    ctx.db.commit()
    return _po(ctx, po)


@router.post("/orders/{oid}/close")
def close_order(oid: int, body: ReasonIn, ctx: Ctx = Depends(need("po.create"))):
    po = svc.close_order(ctx, get_or_404(ctx, PurchaseOrder, oid, "Commande"), body.reason)
    ctx.db.commit()
    return _po(ctx, po)


# ---- réceptions
@router.post("/receipts")
def create_receipt(body: GRIn, ctx: Ctx = Depends(need("receipt.create"))):
    gr = svc.create_receipt(ctx, body.model_dump())
    ctx.db.commit()
    return ser(gr, lines=[ser(l) for l in gr.lines])


@router.get("/receipts")
def list_receipts(order_id: int | None = None, ctx: Ctx = Depends(need("read"))):
    q = select(GoodsReceipt).where(GoodsReceipt.company_id == ctx.company_id)
    if order_id:
        q = q.where(GoodsReceipt.order_id == order_id)
    return [ser(r, lines=[ser(l) for l in r.lines]) for r in ctx.db.scalars(q.order_by(GoodsReceipt.id.desc()))]


# ---- engagements
@router.get("/commitments")
def commitments(format: str | None = None, ctx: Ctx = Depends(need("read"))):
    rows = svc.commitments(ctx)
    if format:
        cols = [("numero", "Bon de commande"), ("fournisseur", "Fournisseur"), ("date_commande", "Date"),
                ("livraison_prevue", "Livraison prévue"), ("devise", "Devise"), ("restant_ht", "Restant HT"),
                ("restant_ttc", "Restant TTC"), ("restant_ttc_tnd", "Restant TTC (TND)"),
                ("recu_non_facture_ht", "Reçu non facturé HT"), ("statut", "Statut")]
        return file_response(format, "État des engagements non facturés", cols, rows)
    return rows


@router.get("/received-not-invoiced")
def received_not_invoiced(ctx: Ctx = Depends(need("read"))):
    out = []
    for po in ctx.db.scalars(select(PurchaseOrder).where(PurchaseOrder.company_id == ctx.company_id,
                                                         PurchaseOrder.status.in_(svc.OPEN_PO + ("cloturee",)))):
        for l in po.lines:
            q = D(l.qty_received) - D(l.qty_invoiced)
            if q > 0:
                out.append({"order_id": po.id, "numero": po.number, "supplier_id": po.supplier_id,
                            "fournisseur": ctx.db.get(Supplier, po.supplier_id).legal_name, "ligne_id": l.id,
                            "description": l.description, "qte_non_facturee": r3(q), "prix": l.unit_price,
                            "montant_ht": r3(q * D(l.unit_price)), "compte": l.account_code})
    return out


_ = PurchaseOrderLine
