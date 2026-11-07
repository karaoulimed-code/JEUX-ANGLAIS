"""Fichier clients, pièces justificatives, grand livre et encours."""
import hashlib
import os
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import audit
from ..config import get_settings
from ..db import get_db
from ..models import Attachment, AuditLog, Customer, Invoice, Payment, RiskSnapshot, User
from ..permissions import has_permission
from ..security import get_current_user, require
from ..services import approvals
from ..services.ledger import customer_exposure, ledger
from .common import check_customer_access, ip, out, scoped
from .schemas import CustomerIn

router = APIRouter(tags=["Clients"])

FIELDS = [f for f in CustomerIn.model_fields if f not in ("code",)]


def customer_dict(c: Customer, detail: bool = False) -> dict:
    d = {"id": c.id, "code": c.code, "legal_name": c.legal_name, "trade_name": c.trade_name, "tax_id": c.tax_id, "city": c.city,
         "phone": c.phone, "email": c.email, "category_code": c.category_code, "sector_code": c.sector_code, "zone_code": c.zone_code,
         "group_code": c.group_code, "salesperson_id": c.salesperson_id,
         "salesperson_name": c.salesperson.full_name if c.salesperson else None, "payment_terms_days": c.payment_terms_days,
         "credit_limit": c.credit_limit, "max_exposure": c.max_exposure, "status": c.status, "in_litigation": c.in_litigation,
         "risk_score": c.risk_score, "risk_class": c.risk_class, "currency": c.currency, "is_demo": c.is_demo}
    if detail:
        d.update({f: getattr(c, f) for f in FIELDS})
        d.update({"rne_id": c.rne_id, "risk_computed_at": c.risk_computed_at, "created_at": c.created_at, "updated_at": c.updated_at})
    return d


@router.get("/customers")
def list_customers(q: str | None = None, status: str | None = None, risk_class: str | None = None, category_code: str | None = None,
                   sector_code: str | None = None, zone_code: str | None = None, group_code: str | None = None,
                   salesperson_id: int | None = None, with_balance: bool = True, limit: int = 500, offset: int = 0,
                   user: User = Depends(require("customers.read")), db: Session = Depends(get_db)):
    stmt = select(Customer).order_by(Customer.legal_name)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Customer.legal_name.ilike(like), Customer.code.ilike(like), Customer.trade_name.ilike(like),
                              Customer.tax_id.ilike(like), Customer.city.ilike(like)))
    for col, val in ((Customer.status, status), (Customer.risk_class, risk_class), (Customer.category_code, category_code),
                     (Customer.sector_code, sector_code), (Customer.zone_code, zone_code), (Customer.group_code, group_code),
                     (Customer.salesperson_id, salesperson_id)):
        if val not in (None, ""):
            stmt = stmt.where(col == val)
    if scoped(user):
        stmt = stmt.where(Customer.salesperson_id == user.id)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar()
    custs = list(db.execute(stmt.limit(min(limit, 2000)).offset(offset)).scalars())
    rows = []
    bal = {}
    if with_balance and custs:
        from ..models import Installment
        from sqlalchemy import case
        import datetime as dt
        q2 = (select(Invoice.customer_id, func.sum(Installment.amount_tnd - Installment.paid_amount_tnd),
                     func.sum(case((Installment.due_date < dt.date.today(), Installment.amount_tnd - Installment.paid_amount_tnd), else_=0)))
              .join(Installment, Installment.invoice_id == Invoice.id)
              .where(Invoice.lifecycle == "VALIDEE", Invoice.doc_type == "FACTURE", Invoice.customer_id.in_([c.id for c in custs]))
              .group_by(Invoice.customer_id))
        bal = {cid: (o, od) for cid, o, od in db.execute(q2)}
    for c in custs:
        d = customer_dict(c)
        o, od = bal.get(c.id, (0, 0))
        d["open_tnd"] = o or 0
        d["overdue_tnd"] = od or 0
        rows.append(d)
    return out({"total": total, "rows": rows})


def _next_code(db: Session) -> str:
    n = db.execute(select(func.count(Customer.id))).scalar() + 1
    while True:
        code = f"C{n:05d}"
        if not db.execute(select(Customer.id).where(Customer.code == code)).first():
            return code
        n += 1


@router.post("/customers")
def create_customer(body: CustomerIn, request: Request, user: User = Depends(require("customers.write")), db: Session = Depends(get_db)):
    code = body.code or _next_code(db)
    if db.execute(select(Customer.id).where(Customer.code == code)).first():
        raise HTTPException(409, "Code client déjà utilisé")
    if body.tax_id and db.execute(select(Customer.id).where(Customer.tax_id == body.tax_id)).first():
        raise HTTPException(409, "Un client possède déjà ce matricule fiscal")
    data = body.model_dump(exclude={"code"})
    if not has_permission(user.role, "customers.credit_limit") and (data["credit_limit"] or data["max_exposure"]):
        raise HTTPException(403, "La fixation d'un plafond de crédit relève du directeur financier")
    if scoped(user):
        data["salesperson_id"] = user.id
    c = Customer(code=code, **data)
    db.add(c)
    db.flush()
    audit.log(db, user, "CUSTOMER_CREATED", "customer", c.id, {"code": code, **data}, ip(request))
    db.commit()
    return out(customer_dict(c, True), 201)


@router.get("/customers/{cid}")
def get_customer(cid: int, user: User = Depends(require("customers.read")), db: Session = Depends(get_db)):
    c = check_customer_access(db, user, cid)
    d = customer_dict(c, True)
    d["exposure"] = customer_exposure(db, cid)
    d["attachments"] = [{"id": a.id, "filename": a.filename, "size": a.size, "description": a.description, "uploaded_at": a.uploaded_at}
                        for a in db.execute(select(Attachment).where(Attachment.entity_type == "customer", Attachment.entity_id == cid)).scalars()]
    d["incidents"] = [{"date": p.rejected_date, "number": p.number, "reference": p.reference, "amount": p.amount_tnd, "reason": p.rejection_reason}
                      for p in db.execute(select(Payment).where(Payment.customer_id == cid, Payment.status == "REJETE").order_by(Payment.rejected_date.desc())).scalars()]
    d["risk_history"] = [{"as_of": s.as_of, "score": s.score, "risk_class": s.risk_class, "computed_at": s.computed_at}
                         for s in db.execute(select(RiskSnapshot).where(RiskSnapshot.customer_id == cid).order_by(RiskSnapshot.id.desc()).limit(24)).scalars()]
    return out(d)


@router.put("/customers/{cid}")
def update_customer(cid: int, body: CustomerIn, request: Request, user: User = Depends(require("customers.write")), db: Session = Depends(get_db)):
    c = check_customer_access(db, user, cid)
    data = body.model_dump(exclude={"code"})
    before = {f: getattr(c, f) for f in FIELDS}
    pending = None
    # Le plafond et l'encours maximal ne se modifient que par demande validée par un tiers
    if data["credit_limit"] != c.credit_limit or data["max_exposure"] != c.max_exposure:
        pending = approvals.request(db, user, "CREDIT_LIMIT", "customer", c.id,
                                    {"credit_limit": str(data["credit_limit"]), "max_exposure": str(data["max_exposure"]),
                                     "old_credit_limit": str(c.credit_limit), "old_max_exposure": str(c.max_exposure)},
                                    request.headers.get("x-reason") or "Révision du plafond de crédit demandée depuis la fiche client")
    data.pop("credit_limit")
    data.pop("max_exposure")
    if scoped(user):
        data["salesperson_id"] = c.salesperson_id
    for k, v in data.items():
        setattr(c, k, v)
    changes = {k: {"old": before[k], "new": v} for k, v in data.items() if before.get(k) != v}
    if changes:
        audit.log(db, user, "CUSTOMER_UPDATED", "customer", c.id, changes, ip(request))
    db.commit()
    res = customer_dict(c, True)
    res["pending_approval"] = pending.id if pending else None
    return out(res)


@router.post("/customers/{cid}/status")
def request_status(cid: int, body: dict, user: User = Depends(require("customers.write")), db: Session = Depends(get_db)):
    c = check_customer_access(db, user, cid)
    st = body.get("status")
    if st not in ("ACTIF", "BLOQUE", "ARCHIVE"):
        raise HTTPException(400, "Statut invalide")
    r = approvals.request(db, user, "CUSTOMER_BLOCK", "customer", c.id, {"status": st, "old": c.status}, body.get("reason") or "")
    db.commit()
    return out({"approval_id": r.id})


@router.get("/customers/{cid}/ledger")
def customer_ledger(cid: int, date_from: str | None = None, date_to: str | None = None,
                    user: User = Depends(require("customers.read")), db: Session = Depends(get_db)):
    import datetime as dt
    check_customer_access(db, user, cid)
    return out(ledger(db, cid, dt.date.fromisoformat(date_from) if date_from else None, dt.date.fromisoformat(date_to) if date_to else None))


@router.get("/customers/{cid}/history")
def customer_history(cid: int, user: User = Depends(require("customers.read")), db: Session = Depends(get_db)):
    check_customer_access(db, user, cid)
    rows = db.execute(select(AuditLog).where(AuditLog.entity_type == "customer", AuditLog.entity_id == str(cid)).order_by(AuditLog.id.desc()).limit(200)).scalars()
    return out([{"ts": r.ts, "username": r.username, "action": r.action, "details": r.details} for r in rows])


# ------------------------------------------------------------------ pièces justificatives
ALLOWED = {".pdf", ".png", ".jpg", ".jpeg", ".xlsx", ".xls", ".docx", ".doc", ".csv", ".txt", ".msg", ".eml"}


@router.post("/attachments")
async def upload(request: Request, entity_type: str = Form(...), entity_id: int = Form(...), description: str | None = Form(None),
                 file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = get_settings()
    if entity_type not in ("customer", "invoice", "payment", "dunning", "provision"):
        raise HTTPException(400, "Type d'entité invalide")
    perm = {"customer": "customers.write", "invoice": "invoices.write", "payment": "payments.write", "dunning": "dunning.write",
            "provision": "provisions.propose"}[entity_type]
    if not has_permission(user.role, perm):
        raise HTTPException(403, "Droit insuffisant")
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED:
        raise HTTPException(400, f"Type de fichier non autorisé ({ext})")
    content = await file.read()
    if len(content) > s.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, "Fichier trop volumineux")
    if entity_type == "customer":
        check_customer_access(db, user, entity_id)
    os.makedirs(s.storage_dir, exist_ok=True)
    name = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(s.storage_dir, name)
    with open(path, "wb") as fh:
        fh.write(content)
    a = Attachment(entity_type=entity_type, entity_id=entity_id, filename=os.path.basename(file.filename or name)[:255],
                   content_type=file.content_type, size=len(content), sha256=hashlib.sha256(content).hexdigest(),
                   storage_path=name, description=description, uploaded_by=user.id)
    db.add(a)
    db.flush()
    audit.log(db, user, "ATTACHMENT_ADDED", entity_type, entity_id, {"file": a.filename, "sha256": a.sha256}, ip(request))
    db.commit()
    return out({"id": a.id, "filename": a.filename, "size": a.size}, 201)


@router.get("/attachments")
def list_attachments(entity_type: str, entity_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(Attachment).where(Attachment.entity_type == entity_type, Attachment.entity_id == entity_id)).scalars()
    return out([{"id": a.id, "filename": a.filename, "size": a.size, "description": a.description, "uploaded_at": a.uploaded_at} for a in rows])


@router.get("/attachments/{aid}")
def download(aid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = db.get(Attachment, aid)
    if not a:
        raise HTTPException(404, "Pièce introuvable")
    if a.entity_type == "customer":
        check_customer_access(db, user, a.entity_id)
    path = os.path.join(get_settings().storage_dir, a.storage_path)
    if not os.path.exists(path):
        raise HTTPException(410, "Fichier absent du stockage (restaurer la sauvegarde des pièces)")
    return FileResponse(path, filename=a.filename, media_type=a.content_type or "application/octet-stream")
