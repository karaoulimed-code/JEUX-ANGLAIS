"""Encaissements, lettrage, portefeuille de chèques et effets."""
import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..models import Allocation, Customer, Invoice, Payment, User
from ..security import require
from ..services import approvals, payments as svc
from .common import MEDIA, check_customer_access, file_response, ip, out, scoped
from .schemas import ManualAllocIn, PaymentIn, ReasonIn, StatusIn

router = APIRouter(tags=["Encaissements"])


def _load(db, user, pid, lock=False) -> Payment:
    q = select(Payment).where(Payment.id == pid)
    if lock:
        q = q.with_for_update()
    p = db.execute(q).scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Règlement introuvable")
    check_customer_access(db, user, p.customer_id)
    return p


def _alloc_rows(db, p: Payment):
    rows = db.execute(select(Allocation).where(Allocation.payment_id == p.id).order_by(Allocation.id)).scalars()
    return [{"id": a.id, "invoice_id": a.invoice_id, "invoice_number": a.invoice.number, "installment_seq": a.installment.seq,
             "date": a.allocation_date, "amount": a.amount, "amount_tnd": a.amount_tnd, "fx_difference_tnd": a.fx_difference_tnd,
             "reversed": a.reversed_at is not None, "reversed_date": a.reversed_date, "reversal_reason": a.reversal_reason} for a in rows]


@router.get("/payments")
def list_payments(q: str | None = None, customer_id: int | None = None, status: str | None = None, method_kind: str | None = None,
                  date_from: dt.date | None = None, date_to: dt.date | None = None, unallocated: bool = False,
                  limit: int = 200, offset: int = 0, user: User = Depends(require("payments.read")), db: Session = Depends(get_db)):
    stmt = select(Payment).join(Customer, Customer.id == Payment.customer_id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Payment.number.ilike(like), Payment.reference.ilike(like), Customer.legal_name.ilike(like), Customer.code.ilike(like)))
    if customer_id:
        stmt = stmt.where(Payment.customer_id == customer_id)
    if status:
        stmt = stmt.where(Payment.status.in_(status.split(",")))
    if method_kind:
        stmt = stmt.where(Payment.method_kind == method_kind)
    if date_from:
        stmt = stmt.where(Payment.receipt_date >= date_from)
    if date_to:
        stmt = stmt.where(Payment.receipt_date <= date_to)
    if unallocated:
        stmt = stmt.where(Payment.amount > Payment.allocated_amount, Payment.status.not_in(["REJETE", "ANNULE"]))
    if scoped(user):
        stmt = stmt.where(Customer.salesperson_id == user.id)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar()
    rows = db.execute(stmt.order_by(Payment.receipt_date.desc(), Payment.id.desc()).limit(min(limit, 2000)).offset(offset)).scalars()
    return out({"total": total, "rows": [svc.payment_dict(p) for p in rows]})


@router.post("/payments")
def create_payment(body: PaymentIn, request: Request, user: User = Depends(require("payments.write")), db: Session = Depends(get_db)):
    check_customer_access(db, user, body.customer_id)
    p, allocs = svc.create_payment(db, user, body.model_dump())
    audit.log(db, user, "PAYMENT_CREATED", "payment", p.id, {"number": p.number, "customer": p.customer.code, "amount": str(p.amount),
                                                             "currency": p.currency, "method": p.method.code, "reference": p.reference,
                                                             "allocations": [{"invoice": a.invoice.number, "amount": str(a.amount)} for a in allocs]},
              ip(request))
    db.commit()
    d = svc.payment_dict(p)
    d["allocations"] = _alloc_rows(db, p)
    return out(d, 201)


@router.get("/payments/{pid}")
def get_payment(pid: int, user: User = Depends(require("payments.read")), db: Session = Depends(get_db)):
    p = _load(db, user, pid)
    d = svc.payment_dict(p)
    d["allocations"] = _alloc_rows(db, p)
    return out(d)


@router.post("/payments/{pid}/allocate")
def allocate(pid: int, body: ManualAllocIn, request: Request, user: User = Depends(require("allocations.write")), db: Session = Depends(get_db)):
    p = _load(db, user, pid, lock=True)
    src = svc.Source(p)
    done = []
    for item in body.allocations:
        inv = db.execute(select(Invoice).where(Invoice.id == item.invoice_id).with_for_update()).scalar_one_or_none()
        if not inv:
            raise HTTPException(404, "Facture introuvable")
        done += svc.allocate_invoice(db, user, src, inv, item.amount, body.date or p.receipt_date)
    audit.log(db, user, "PAYMENT_ALLOCATED", "payment", p.id, {"allocations": [{"invoice": a.invoice.number, "amount": str(a.amount)} for a in done]}, ip(request))
    db.commit()
    d = svc.payment_dict(p)
    d["allocations"] = _alloc_rows(db, p)
    return out(d)


@router.post("/payments/{pid}/auto-allocate")
def auto_allocate(pid: int, request: Request, user: User = Depends(require("allocations.write")), db: Session = Depends(get_db)):
    p = _load(db, user, pid, lock=True)
    done = svc.auto_allocate(db, user, svc.Source(p), dt.date.today())
    audit.log(db, user, "PAYMENT_AUTO_ALLOCATED", "payment", p.id, {"allocations": [{"invoice": a.invoice.number, "amount": str(a.amount)} for a in done]}, ip(request))
    db.commit()
    d = svc.payment_dict(p)
    d["allocations"] = _alloc_rows(db, p)
    return out(d)


@router.post("/allocations/{aid}/reverse")
def reverse(aid: int, body: ReasonIn, request: Request, user: User = Depends(require("allocations.write")), db: Session = Depends(get_db)):
    a = db.get(Allocation, aid)
    if not a:
        raise HTTPException(404, "Affectation introuvable")
    check_customer_access(db, user, a.customer_id)
    if a.adjustment_id:
        raise HTTPException(409, "Une OD validée (écart, passage en perte) ne peut pas être délettrée")
    if not body.reason or len(body.reason) < 5:
        raise HTTPException(400, "Motif obligatoire")
    svc.reverse_allocation(db, user, a, body.reason)
    audit.log(db, user, "ALLOCATION_REVERSED", "invoice", a.invoice_id, {"allocation": a.id, "amount": str(a.amount), "reason": body.reason}, ip(request))
    db.commit()
    return out({"ok": True})


@router.post("/payments/{pid}/status")
def change_status(pid: int, body: StatusIn, request: Request, user: User = Depends(require("payments.status")), db: Session = Depends(get_db)):
    p = _load(db, user, pid, lock=True)
    old = p.status
    svc.change_status(db, user, p, body.status, body.date, body.reason)
    audit.log(db, user, "PAYMENT_STATUS", "payment", p.id, {"old": old, "new": body.status, "date": body.date, "reason": body.reason}, ip(request))
    db.commit()
    return out(svc.payment_dict(p))


@router.post("/payments/{pid}/cancel-request")
def cancel_request(pid: int, body: ReasonIn, user: User = Depends(require("payments.write")), db: Session = Depends(get_db)):
    p = _load(db, user, pid)
    r = approvals.request(db, user, "PAYMENT_CANCEL", "payment", p.id, {"number": p.number, "amount": str(p.amount)}, body.reason)
    db.commit()
    return out({"approval_id": r.id})


@router.get("/payments/{pid}/receipt")
def receipt(pid: int, user: User = Depends(require("payments.read")), db: Session = Depends(get_db)):
    from ..services.printing import receipt_pdf
    p = _load(db, user, pid)
    return file_response(receipt_pdf(db, p), f"recu_{p.number}.pdf", MEDIA["pdf"])


@router.get("/customers/{cid}/open-invoices")
def open_invoices(cid: int, currency: str = "TND", user: User = Depends(require("payments.read")), db: Session = Depends(get_db)):
    check_customer_access(db, user, cid)
    from ..services.invoices import invoice_dict
    invs = db.execute(select(Invoice).where(Invoice.customer_id == cid, Invoice.doc_type == "FACTURE", Invoice.lifecycle == "VALIDEE",
                                            Invoice.balance > 0, Invoice.currency == currency).order_by(Invoice.due_date)).scalars()
    cns = db.execute(select(Invoice).where(Invoice.customer_id == cid, Invoice.doc_type == "AVOIR", Invoice.lifecycle == "VALIDEE",
                                           Invoice.balance > 0)).scalars()
    unalloc = db.execute(select(Payment).where(Payment.customer_id == cid, Payment.amount > Payment.allocated_amount,
                                               Payment.status.not_in(["REJETE", "ANNULE"]))).scalars()
    return out({"invoices": [invoice_dict(i) for i in invs], "credit_notes": [invoice_dict(c) for c in cns],
                "unallocated_payments": [svc.payment_dict(p) for p in unalloc]})
