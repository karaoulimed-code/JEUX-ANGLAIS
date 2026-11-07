from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import select

from ..models import (BankStatementLine, Invoice, Payment, PaymentRun, Supplier, TreasuryAccount)
from ..schemas import (ExecuteIn, LaterAllocIn, MatchIn, PaymentIn, ReasonIn, RejectIn, RunIn, StatementIn,
                       TreasuryIn, ser)
from ..security import BusinessError, Ctx, need
from ..services import payments as svc
from ..services.analytics import payment_plan
from ..services.common import ctx_audit
from .deps import get_or_404, today

router = APIRouter(prefix="/api/payments", tags=["Module 6 - Règlements et trésorerie"])


def _p(ctx: Ctx, p: Payment) -> dict:
    allocs = []
    for a in p.allocations:
        inv = ctx.db.get(Invoice, a.invoice_id)
        allocs.append(ser(a, facture=inv.internal_ref, numero=inv.supplier_number))
    return ser(p, fournisseur=ctx.db.get(Supplier, p.supplier_id).legal_name, allocations=allocs,
               non_affecte=svc.unallocated(ctx.db, p))


@router.get("")
def list_payments(status: str | None = None, supplier_id: int | None = None, method: str | None = None,
                  ctx: Ctx = Depends(need("read"))):
    q = select(Payment).where(Payment.company_id == ctx.company_id)
    if status:
        q = q.where(Payment.status == status)
    if supplier_id:
        q = q.where(Payment.supplier_id == supplier_id)
    if method:
        q = q.where(Payment.method == method)
    return [_p(ctx, p) for p in ctx.db.scalars(q.order_by(Payment.payment_date.desc(), Payment.id.desc()))]


@router.get("/plan")
def plan(horizon_days: int = 30, cash_available: Decimal | None = None, as_of: date | None = None,
         ctx: Ctx = Depends(need("treasury.read"))):
    return payment_plan(ctx, today(as_of), horizon_days, cash_available)


@router.get("/runs")
def list_runs(ctx: Ctx = Depends(need("read"))):
    out = []
    for r in ctx.db.scalars(select(PaymentRun).where(PaymentRun.company_id == ctx.company_id).order_by(PaymentRun.id.desc())):
        pays = list(ctx.db.scalars(select(Payment).where(Payment.run_id == r.id)))
        out.append(ser(r, reglements=[_p(ctx, p) for p in pays]))
    return out


@router.post("/runs")
def create_run(body: RunIn, ctx: Ctx = Depends(need("payment.prepare"))):
    run, pays, warns = svc.create_run(ctx, body.model_dump())
    ctx.db.commit()
    return {"campagne": ser(run), "reglements": [_p(ctx, p) for p in pays], "avertissements": warns}


@router.post("/runs/{rid}/approve")
def approve_run(rid: int, ctx: Ctx = Depends(need("payment.approve"))):
    run = get_or_404(ctx, PaymentRun, rid, "Campagne")
    done, errors = [], []
    for p in ctx.db.scalars(select(Payment).where(Payment.run_id == run.id, Payment.status == "a_approuver")):
        try:
            svc.approve_payment(ctx, p)
            done.append(p.number)
        except BusinessError as e:
            errors.append({"reglement": p.number, "erreur": e.message})
    if done and not errors:
        run.status = "approuvee"
    ctx_audit(ctx, "approbation", "campagne_paiement", run.id, {"approuves": done, "erreurs": errors})
    ctx.db.commit()
    return {"approuves": done, "erreurs": errors}


@router.get("/{pid}")
def get_payment(pid: int, ctx: Ctx = Depends(need("read"))):
    return _p(ctx, get_or_404(ctx, Payment, pid, "Règlement"))


@router.post("")
def create_payment(body: PaymentIn, ctx: Ctx = Depends(need("payment.prepare"))):
    data = body.model_dump()
    data["allocations"] = [dict(a) for a in data["allocations"]]
    p, warnings = svc.create_payment(ctx, data)
    ctx.db.commit()
    return {"reglement": _p(ctx, p), "avertissements": warnings}


@router.post("/{pid}/submit")
def submit(pid: int, ctx: Ctx = Depends(need("payment.prepare"))):
    p = svc.submit_payment(ctx, get_or_404(ctx, Payment, pid, "Règlement"))
    ctx.db.commit()
    return _p(ctx, p)


@router.post("/{pid}/approve")
def approve(pid: int, ctx: Ctx = Depends(need("payment.approve"))):
    p = svc.approve_payment(ctx, get_or_404(ctx, Payment, pid, "Règlement"))
    ctx.db.commit()
    return _p(ctx, p)


@router.post("/{pid}/execute")
def execute(pid: int, body: ExecuteIn, ctx: Ctx = Depends(need("payment.execute"))):
    p = get_or_404(ctx, Payment, pid, "Règlement")
    if body.reference:
        p.reference = body.reference
    p = svc.execute_payment(ctx, p, body.execution_date)
    ctx.db.commit()
    return _p(ctx, p)


@router.post("/{pid}/reject")
def reject(pid: int, body: RejectIn, ctx: Ctx = Depends(need("bank.reconcile"))):
    p = svc.reject_payment(ctx, get_or_404(ctx, Payment, pid, "Règlement"), body.reason, body.rejection_date)
    ctx.db.commit()
    return _p(ctx, p)


@router.post("/{pid}/cancel")
def cancel(pid: int, body: ReasonIn, ctx: Ctx = Depends(need("payment.prepare"))):
    p = svc.cancel_payment(ctx, get_or_404(ctx, Payment, pid, "Règlement"), body.reason)
    ctx.db.commit()
    return _p(ctx, p)


@router.post("/{pid}/allocate")
def allocate(pid: int, body: LaterAllocIn, ctx: Ctx = Depends(need("payment.prepare"))):
    p = get_or_404(ctx, Payment, pid, "Règlement")
    inv = get_or_404(ctx, Invoice, body.invoice_id, "Facture")
    a = svc.allocate_later(ctx, p, inv, body.amount, body.allocation_date)
    ctx.db.commit()
    return ser(a)


# ------------------------------------------------------------ trésorerie et rapprochement
treasury = APIRouter(prefix="/api/treasury", tags=["Module 6 - Comptes de trésorerie et rapprochement bancaire"])


@treasury.get("/accounts")
def accounts(ctx: Ctx = Depends(need("read"))):
    return [ser(a, **{k: v for k, v in svc.reconciliation_state(ctx, a.id).items() if k in (
        "solde_releve", "paiements_emis_non_debites", "solde_disponible_previsionnel")})
            for a in ctx.db.scalars(select(TreasuryAccount).where(TreasuryAccount.company_id == ctx.company_id))]


@treasury.post("/accounts")
def create_account(body: TreasuryIn, ctx: Ctx = Depends(need("settings.manage"))):
    a = TreasuryAccount(company_id=ctx.company_id, **body.model_dump())
    ctx.db.add(a)
    ctx.db.flush()
    ctx_audit(ctx, "creation", "compte_tresorerie", a.id, {"nom": a.name})
    ctx.db.commit()
    return ser(a)


@treasury.post("/statements")
def import_statement(body: StatementIn, ctx: Ctx = Depends(need("bank.reconcile"))):
    res = svc.import_statement(ctx, body.treasury_account_id, [l.model_dump() for l in body.lines])
    ctx.db.commit()
    return res


@treasury.post("/match")
def match(body: MatchIn, ctx: Ctx = Depends(need("bank.reconcile"))):
    bl = get_or_404(ctx, BankStatementLine, body.statement_line_id, "Ligne de relevé")
    p = get_or_404(ctx, Payment, body.payment_id, "Règlement")
    svc.match_line(ctx, bl, p)
    ctx.db.commit()
    return {"ok": True}


@treasury.get("/accounts/{aid}/reconciliation")
def reconciliation(aid: int, ctx: Ctx = Depends(need("read"))):
    get_or_404(ctx, TreasuryAccount, aid, "Compte")
    return svc.reconciliation_state(ctx, aid)
