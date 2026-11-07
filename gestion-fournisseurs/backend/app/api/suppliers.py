from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import or_, select

from ..models import (Invoice, Payment, PurchaseOrder, Supplier, SupplierBankAccount, SupplierContract,
                      SupplierEvaluation, SupplierIncident)
from ..money import D, ZERO, r3
from ..schemas import (BankAccountIn, ContractIn, EvaluationIn, IncidentIn, StatusIn, SupplierIn, SupplierUpdate,
                       VerifyIn, ser)
from ..security import Ctx, need
from ..services import suppliers as svc
from ..services.analytics import supplier_risk
from ..services.common import ctx_audit
from ..services.invoices import balance, display_status
from .deps import get_or_404, today

router = APIRouter(prefix="/api/suppliers", tags=["Module 1 - Fournisseurs"])


def _summary(ctx: Ctx, s: Supplier) -> dict:
    invs = list(ctx.db.scalars(select(Invoice).where(Invoice.supplier_id == s.id, Invoice.validated_at.is_not(None))))
    due = ZERO
    for i in invs:
        if i.doc_type != "avoir":
            due += max(balance(ctx.db, i), ZERO) * D(i.exchange_rate)
    return ser(s, solde_du_tnd=r3(due),
               rib_verifie=any(b.status == "verifie" for b in s.bank_accounts),
               rib_a_verifier=any(b.status == "a_verifier" for b in s.bank_accounts))


@router.get("")
def list_suppliers(q: str | None = None, category: str | None = None, status: str | None = None,
                   ctx: Ctx = Depends(need("read"))):
    stmt = select(Supplier).where(Supplier.company_id == ctx.company_id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Supplier.legal_name.ilike(like), Supplier.trade_name.ilike(like),
                              Supplier.code.ilike(like), Supplier.tax_id.ilike(like)))
    if category:
        stmt = stmt.where(Supplier.category == category)
    if status:
        stmt = stmt.where(Supplier.status == status)
    return [_summary(ctx, s) for s in ctx.db.scalars(stmt.order_by(Supplier.legal_name))]


@router.post("/check-duplicates")
def check_duplicates(body: dict, ctx: Ctx = Depends(need("read"))):
    return svc.find_duplicates(ctx, body.get("legal_name", ""), body.get("tax_id"), body.get("rib"), body.get("exclude_id"))


@router.post("")
def create_supplier(body: SupplierIn, force: bool = False, ctx: Ctx = Depends(need("supplier.write"))):
    s, warnings = svc.create_supplier(ctx, body.model_dump(), force)
    ctx.db.commit()
    return {"supplier": ser(s), "avertissements": warnings}


@router.get("/{sid}")
def get_supplier(sid: int, ctx: Ctx = Depends(need("read"))):
    s = get_or_404(ctx, Supplier, sid, "Fournisseur")
    invs = list(ctx.db.scalars(select(Invoice).where(Invoice.supplier_id == s.id).order_by(Invoice.invoice_date.desc())))
    risk = next((r for r in supplier_risk(ctx, date.today()) if r["supplier_id"] == s.id), None)
    return {
        **_summary(ctx, s),
        "comptes_bancaires": [ser(b) for b in s.bank_accounts],
        "contrats": [ser(c) for c in ctx.db.scalars(select(SupplierContract).where(SupplierContract.supplier_id == s.id))],
        "incidents": [ser(i) for i in ctx.db.scalars(select(SupplierIncident).where(SupplierIncident.supplier_id == s.id)
                                                     .order_by(SupplierIncident.incident_date.desc()))],
        "evaluations": [ser(e) for e in ctx.db.scalars(select(SupplierEvaluation).where(SupplierEvaluation.supplier_id == s.id)
                                                       .order_by(SupplierEvaluation.id.desc()))],
        "factures": [ser(i, solde=balance(ctx.db, i), statut=display_status(ctx.db, i)) for i in invs[:200]],
        "commandes": [ser(p) for p in ctx.db.scalars(select(PurchaseOrder).where(PurchaseOrder.supplier_id == s.id)
                                                     .order_by(PurchaseOrder.order_date.desc()).limit(100))],
        "reglements": [ser(p) for p in ctx.db.scalars(select(Payment).where(Payment.supplier_id == s.id)
                                                      .order_by(Payment.payment_date.desc()).limit(100))],
        "risque": risk,
    }


@router.patch("/{sid}")
def update_supplier(sid: int, body: SupplierUpdate, ctx: Ctx = Depends(need("supplier.write"))):
    s = get_or_404(ctx, Supplier, sid, "Fournisseur")
    s = svc.update_supplier(ctx, s, body.model_dump(exclude_unset=True))
    ctx.db.commit()
    return ser(s)


@router.post("/{sid}/status")
def set_status(sid: int, body: StatusIn, ctx: Ctx = Depends(need("supplier.approve"))):
    s = svc.approve_supplier(ctx, get_or_404(ctx, Supplier, sid, "Fournisseur"), body.status)
    ctx.db.commit()
    return ser(s)


@router.post("/{sid}/bank-accounts")
def add_bank(sid: int, body: BankAccountIn, ctx: Ctx = Depends(need("supplier.write"))):
    acc, w = svc.add_bank_account(ctx, get_or_404(ctx, Supplier, sid, "Fournisseur"), body.model_dump())
    ctx.db.commit()
    return {"compte": ser(acc), "avertissements": w}


@router.post("/bank-accounts/{aid}/verify")
def verify_bank(aid: int, body: VerifyIn, ctx: Ctx = Depends(need("supplier.bank_verify"))):
    acc = svc.verify_bank_account(ctx, get_or_404(ctx, SupplierBankAccount, aid, "Compte"), body.accept, body.note)
    ctx.db.commit()
    return ser(acc)


@router.post("/{sid}/contracts")
def add_contract(sid: int, body: ContractIn, ctx: Ctx = Depends(need("supplier.write"))):
    s = get_or_404(ctx, Supplier, sid, "Fournisseur")
    c = SupplierContract(company_id=ctx.company_id, supplier_id=s.id, **body.model_dump())
    ctx.db.add(c)
    ctx.db.flush()
    ctx_audit(ctx, "ajout_contrat", "fournisseur", s.id, {"reference": c.reference})
    ctx.db.commit()
    return ser(c)


@router.post("/{sid}/incidents")
def add_incident(sid: int, body: IncidentIn, ctx: Ctx = Depends(need("dispute.manage"))):
    s = get_or_404(ctx, Supplier, sid, "Fournisseur")
    i = SupplierIncident(company_id=ctx.company_id, supplier_id=s.id, created_by_id=ctx.user.id, **body.model_dump())
    ctx.db.add(i)
    ctx.db.flush()
    ctx_audit(ctx, "incident", "fournisseur", s.id, {"type": i.kind})
    ctx.db.commit()
    return ser(i)


@router.post("/{sid}/evaluations")
def add_evaluation(sid: int, body: EvaluationIn, ctx: Ctx = Depends(need("supplier.evaluate"))):
    s = get_or_404(ctx, Supplier, sid, "Fournisseur")
    e = SupplierEvaluation(company_id=ctx.company_id, supplier_id=s.id, evaluated_by_id=ctx.user.id, **body.model_dump())
    ctx.db.add(e)
    ctx.db.flush()
    ctx_audit(ctx, "evaluation", "fournisseur", s.id, body.model_dump())
    ctx.db.commit()
    return ser(e)


@router.get("/analysis/risk")
def risk(as_of: date | None = None, ctx: Ctx = Depends(need("read"))):
    return supplier_risk(ctx, today(as_of))
