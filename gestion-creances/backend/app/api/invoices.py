"""Factures, avoirs, imports."""
import datetime as dt

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..models import Allocation, Customer, Invoice, Payment, Adjustment, User
from ..security import require
from ..services import approvals, imports, invoices as svc, payments as pay_svc
from ..services.params import get_param
from .common import MEDIA, check_customer_access, file_response, ip, out, scoped
from .schemas import ClassifyIn, InvoiceIn, ReasonIn

router = APIRouter(tags=["Factures"])


def _load(db: Session, user: User, iid: int, lock: bool = False) -> Invoice:
    q = select(Invoice).where(Invoice.id == iid)
    if lock:
        q = q.with_for_update()
    inv = db.execute(q).scalar_one_or_none()
    if not inv:
        raise HTTPException(404, "Pièce introuvable")
    check_customer_access(db, user, inv.customer_id)
    return inv


@router.get("/invoices")
def list_invoices(q: str | None = None, customer_id: int | None = None, doc_type: str | None = None, status: str | None = None,
                  classification: str | None = None, currency: str | None = None, date_from: dt.date | None = None,
                  date_to: dt.date | None = None, due_from: dt.date | None = None, due_to: dt.date | None = None,
                  min_amount: float | None = None, max_amount: float | None = None, salesperson_id: int | None = None,
                  source: str | None = None, limit: int = 200, offset: int = 0, sort: str = "-issue_date",
                  user: User = Depends(require("invoices.read")), db: Session = Depends(get_db)):
    today = dt.date.today()
    stmt = select(Invoice).join(Customer, Customer.id == Invoice.customer_id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Invoice.number.ilike(like), Invoice.external_ref.ilike(like), Customer.legal_name.ilike(like),
                              Customer.code.ilike(like), Invoice.order_ref.ilike(like)))
    for col, val in ((Invoice.customer_id, customer_id), (Invoice.doc_type, doc_type), (Invoice.classification, classification),
                     (Invoice.currency, currency), (Invoice.salesperson_id, salesperson_id), (Invoice.source, source)):
        if val not in (None, ""):
            stmt = stmt.where(col == val)
    if status:
        stmt = stmt.where(svc.status_filter(status, today))
    if date_from:
        stmt = stmt.where(Invoice.issue_date >= date_from)
    if date_to:
        stmt = stmt.where(Invoice.issue_date <= date_to)
    if due_from:
        stmt = stmt.where(Invoice.due_date >= due_from)
    if due_to:
        stmt = stmt.where(Invoice.due_date <= due_to)
    if min_amount is not None:
        stmt = stmt.where(Invoice.total_ttc >= min_amount)
    if max_amount is not None:
        stmt = stmt.where(Invoice.total_ttc <= max_amount)
    if scoped(user):
        stmt = stmt.where(Customer.salesperson_id == user.id)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar()
    col = {"issue_date": Invoice.issue_date, "due_date": Invoice.due_date, "number": Invoice.number, "total_ttc": Invoice.total_ttc,
           "balance": Invoice.balance, "customer": Customer.legal_name}.get(sort.lstrip("-"), Invoice.issue_date)
    stmt = stmt.order_by(col.desc() if sort.startswith("-") else col.asc(), Invoice.id.desc())
    rows = [svc.invoice_dict(i, today) for i in db.execute(stmt.limit(min(limit, 2000)).offset(offset)).scalars()]
    return out({"total": total, "rows": rows})


@router.post("/invoices")
def create_invoice(body: InvoiceIn, request: Request, user: User = Depends(require("invoices.write")), db: Session = Depends(get_db)):
    check_customer_access(db, user, body.customer_id)
    if body.doc_type not in ("FACTURE", "AVOIR"):
        raise HTTPException(400, "Type de pièce invalide")
    data = body.model_dump()
    inv = svc.save_draft(db, user, data)
    audit.log(db, user, "INVOICE_DRAFT_CREATED", "invoice", inv.id, {"doc_type": inv.doc_type, "customer": inv.customer.code,
                                                                     "ttc": str(inv.total_ttc)}, ip(request))
    dups = svc.find_duplicates(db, inv.customer_id, inv.issue_date, inv.total_ttc, inv.external_ref, exclude_id=inv.id)
    db.commit()
    res = svc.invoice_dict(inv, detail=True)
    res["duplicate_warnings"] = [d.number or f"brouillon #{d.id}" for d in dups]
    return out(res, 201)


@router.get("/invoices/{iid}")
def get_invoice(iid: int, user: User = Depends(require("invoices.read")), db: Session = Depends(get_db)):
    inv = _load(db, user, iid)
    d = svc.invoice_dict(inv, detail=True)
    allocs = db.execute(select(Allocation).where(or_(Allocation.invoice_id == iid, Allocation.credit_note_id == iid))
                        .order_by(Allocation.allocation_date, Allocation.id)).scalars()
    d["allocations"] = []
    for a in allocs:
        if a.payment_id:
            src = db.get(Payment, a.payment_id)
            src_label = f"Règlement {src.number} ({src.method.label})"
        elif a.credit_note_id:
            src = db.get(Invoice, a.credit_note_id)
            src_label = f"Avoir {src.number}"
        else:
            src = db.get(Adjustment, a.adjustment_id)
            src_label = f"OD {src.number} ({src.kind})"
        d["allocations"].append({"id": a.id, "date": a.allocation_date, "source": src_label, "invoice_number": a.invoice.number,
                                 "installment_seq": a.installment.seq, "amount": a.amount, "amount_tnd": a.amount_tnd,
                                 "fx_difference_tnd": a.fx_difference_tnd, "reversed": a.reversed_at is not None,
                                 "reversed_date": a.reversed_date, "reversal_reason": a.reversal_reason})
    d["credit_notes"] = [svc.invoice_dict(c) for c in db.execute(select(Invoice).where(Invoice.related_invoice_id == iid)).scalars()]
    d["customer_tax_id"] = inv.customer.tax_id
    d["customer_address"] = inv.customer.address
    return out(d)


@router.put("/invoices/{iid}")
def update_invoice(iid: int, body: InvoiceIn, request: Request, user: User = Depends(require("invoices.write")), db: Session = Depends(get_db)):
    inv = _load(db, user, iid, lock=True)
    before = {"ttc": str(inv.total_ttc), "customer": inv.customer_id}
    svc.save_draft(db, user, body.model_dump(), inv)
    audit.log(db, user, "INVOICE_DRAFT_UPDATED", "invoice", inv.id, {"before": before, "ttc": str(inv.total_ttc)}, ip(request))
    db.commit()
    return out(svc.invoice_dict(inv, detail=True))


@router.delete("/invoices/{iid}")
def delete_draft(iid: int, request: Request, user: User = Depends(require("invoices.write")), db: Session = Depends(get_db)):
    inv = _load(db, user, iid, lock=True)
    if inv.lifecycle != "BROUILLON":
        raise HTTPException(409, "Une pièce validée ne peut pas être supprimée : émettez un avoir")
    audit.log(db, user, "INVOICE_DRAFT_DELETED", "invoice", inv.id, {"ttc": str(inv.total_ttc), "customer": inv.customer.code}, ip(request))
    db.delete(inv)
    db.commit()
    return out({"ok": True})


@router.post("/invoices/{iid}/validate")
def validate_invoice(iid: int, request: Request, force: bool = False, user: User = Depends(require("invoices.validate")),
                     db: Session = Depends(get_db)):
    inv = _load(db, user, iid, lock=True)
    res = svc.validate(db, user, inv, force)
    audit.log(db, user, "INVOICE_VALIDATED", "invoice", inv.id, {"number": inv.number, "ttc": str(inv.total_ttc),
                                                                 "currency": inv.currency, "warnings": res["warnings"]}, ip(request))
    allocs = []
    if inv.doc_type == "AVOIR" and inv.related_invoice_id:
        rel = db.get(Invoice, inv.related_invoice_id)
        if rel.balance > 0 and rel.currency == inv.currency:
            allocs = pay_svc.allocate_invoice(db, user, pay_svc.Source(inv), rel, min(rel.balance, inv.total_ttc), inv.issue_date)
            audit.log(db, user, "CREDIT_NOTE_IMPUTED", "invoice", rel.id, {"credit_note": inv.number, "amount": str(sum(a.amount for a in allocs))}, ip(request))
    db.commit()
    out_ = svc.invoice_dict(inv, detail=True)
    out_["warnings"] = res["warnings"]
    return out(out_)


@router.post("/invoices/{iid}/classify")
def classify(iid: int, body: ClassifyIn, request: Request, user: User = Depends(require("invoices.classify")), db: Session = Depends(get_db)):
    inv = _load(db, user, iid, lock=True)
    old = inv.classification
    svc.classify(db, user, inv, body.classification, body.reason)
    audit.log(db, user, "INVOICE_CLASSIFIED", "invoice", inv.id, {"old": old, "new": body.classification, "reason": body.reason}, ip(request))
    db.commit()
    return out(svc.invoice_dict(inv, detail=True))


@router.post("/invoices/{iid}/write-off-request")
def write_off(iid: int, body: ReasonIn, user: User = Depends(require("invoices.classify")), db: Session = Depends(get_db)):
    inv = _load(db, user, iid)
    r = approvals.request(db, user, "WRITE_OFF", "invoice", inv.id, {"number": inv.number, "customer": inv.customer.code}, body.reason)
    db.commit()
    return out({"approval_id": r.id, "message": "Demande transmise pour validation par le directeur financier"})


@router.post("/invoices/{iid}/settle-difference")
def settle_difference(iid: int, body: ReasonIn, request: Request, user: User = Depends(require("adjustments.write")), db: Session = Depends(get_db)):
    inv = _load(db, user, iid, lock=True)
    adj = pay_svc.settle_small_difference(db, user, inv, body.reason)
    audit.log(db, user, "SMALL_DIFFERENCE_SETTLED", "invoice", inv.id, {"adjustment": adj.number, "amount": str(adj.amount)}, ip(request))
    db.commit()
    return out(svc.invoice_dict(inv, detail=True))


@router.post("/invoices/{iid}/impute-credit-note")
def impute_credit_note(iid: int, body: dict, request: Request, user: User = Depends(require("allocations.write")), db: Session = Depends(get_db)):
    """Imputation d'un avoir validé (iid) sur une facture du même client."""
    cn = _load(db, user, iid, lock=True)
    inv = _load(db, user, int(body["invoice_id"]), lock=True)
    amount = body.get("amount") or min(cn.balance, inv.balance)
    allocs = pay_svc.allocate_invoice(db, user, pay_svc.Source(cn), inv, amount)
    audit.log(db, user, "CREDIT_NOTE_IMPUTED", "invoice", inv.id, {"credit_note": cn.number, "amount": str(amount)}, ip(request))
    db.commit()
    return out({"allocations": len(allocs)})


@router.get("/invoices/{iid}/pdf")
def invoice_pdf(iid: int, user: User = Depends(require("invoices.read")), db: Session = Depends(get_db)):
    from ..services.printing import invoice_pdf as render
    inv = _load(db, user, iid)
    return file_response(render(db, inv), f"{inv.number or 'brouillon'}.pdf", MEDIA["pdf"])


# ------------------------------------------------------------------ imports
@router.post("/imports/{kind}")
async def do_import(kind: str, request: Request, dry_run: bool = Form(True), file: UploadFile = File(...),
                    user: User = Depends(require("imports.write")), db: Session = Depends(get_db)):
    content = await file.read()
    if kind == "invoices":
        res = imports.import_invoices(db, user, file.filename or "", content, dry_run)
    elif kind == "customers":
        res = imports.import_customers(db, user, file.filename or "", content, dry_run)
    else:
        raise HTTPException(404, "Type d'import inconnu")
    if not dry_run and res.get("imported"):
        audit.log(db, user, "IMPORT", kind, None, {"file": file.filename, "imported": res["imported"]}, ip(request))
        db.commit()
    return out(res)


@router.get("/imports/{kind}/template")
def import_template(kind: str, user: User = Depends(require("imports.write"))):
    from ..services.exports import to_xlsx
    cols = imports.INVOICE_COLUMNS if kind == "invoices" else imports.CUSTOMER_COLUMNS
    example = ({"numero": "F-2026-001", "date": "15/01/2026", "code_client": "C00001", "echeance": "15/02/2026", "montant_ht": 1000,
                "tva": 190, "autres_taxes": 1, "montant_ttc": 1191, "devise": "TND", "cours": "", "reference_externe": "", "type": "FACTURE"}
               if kind == "invoices" else {"code": "C00001", "raison_sociale": "SOCIETE EXEMPLE SARL", "delai_paiement_jours": 60})
    content = to_xlsx(f"Modèle import {kind}", [{"key": c, "label": c} for c in cols], [example])
    return file_response(content, f"modele_import_{kind}.xlsx", MEDIA["xlsx"])
