from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import select

from ..models import Dispute, Invoice, Supplier
from ..money import D
from ..schemas import DisputeIn, DisputeUpdate, ser
from ..security import BusinessError, Ctx, need
from ..services.common import ctx_audit, next_number
from ..services.invoices import balance
from .deps import get_or_404

router = APIRouter(prefix="/api/disputes", tags=["Module 7 - Litiges"])


@router.get("")
def list_disputes(status: str | None = None, supplier_id: int | None = None, ctx: Ctx = Depends(need("read"))):
    q = select(Dispute).where(Dispute.company_id == ctx.company_id)
    if status:
        q = q.where(Dispute.status == status)
    if supplier_id:
        q = q.where(Dispute.supplier_id == supplier_id)
    out = []
    for d in ctx.db.scalars(q.order_by(Dispute.opened_at.desc())):
        inv = ctx.db.get(Invoice, d.invoice_id) if d.invoice_id else None
        out.append(ser(d, fournisseur=ctx.db.get(Supplier, d.supplier_id).legal_name,
                       facture=inv.internal_ref if inv else None))
    return out


@router.post("")
def create_dispute(body: DisputeIn, ctx: Ctx = Depends(need("dispute.manage"))):
    get_or_404(ctx, Supplier, body.supplier_id, "Fournisseur")
    if body.invoice_id:
        inv = get_or_404(ctx, Invoice, body.invoice_id, "Facture")
        if inv.supplier_id != body.supplier_id:
            raise BusinessError("La facture n'appartient pas à ce fournisseur.")
        if D(body.contested_amount) > max(balance(ctx.db, inv), D(0)) and inv.workflow_status == "validee":
            raise BusinessError("Montant contesté supérieur au solde restant dû de la facture.")
    d = Dispute(company_id=ctx.company_id, created_by_id=ctx.user.id,
                number=next_number(ctx.db, ctx.company_id, "LT", body.opened_at),
                **{**body.model_dump(), "owner_id": body.owner_id or ctx.user.id})
    ctx.db.add(d)
    ctx.db.flush()
    ctx_audit(ctx, "ouverture", "litige", d.id, {"numero": d.number, "montant": d.contested_amount, "motif": d.kind})
    ctx.db.commit()
    return ser(d)


@router.patch("/{did}")
def update_dispute(did: int, body: DisputeUpdate, ctx: Ctx = Depends(need("dispute.manage"))):
    d = get_or_404(ctx, Dispute, did, "Litige")
    if d.status == "clos":
        raise BusinessError("Litige clos : non modifiable.")
    data = body.model_dump(exclude_unset=True)
    if data.get("status") in ("resolu", "clos") and not (data.get("decision") or d.decision):
        raise BusinessError("La décision finale doit être renseignée pour résoudre ou clore un litige.")
    before = {k: getattr(d, k) for k in data}
    for k, v in data.items():
        setattr(d, k, v)
    if d.status in ("resolu", "clos") and not d.closed_at:
        d.closed_at = date.today()
    ctx_audit(ctx, "mise_a_jour", "litige", d.id, {"avant": before, "apres": data})
    ctx.db.commit()
    return ser(d)
