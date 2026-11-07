"""Recouvrement, risque, provisions, approbations."""
import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..models import ApprovalRequest, Customer, DunningAction, Invoice, Provision, ProvisionCampaign, User
from ..permissions import has_permission
from ..security import get_current_user, require
from ..services import approvals, dunning, provisions, risk
from .common import check_customer_access, ip, out, scoped
from .schemas import ApprovalIn, DecisionIn, DunningActionIn, PreviewIn, ProvisionLineIn, ProvisionProposeIn

router = APIRouter()


# ------------------------------------------------------------------ recouvrement
@router.get("/dunning/proposals", tags=["Recouvrement"])
def proposals(as_of: dt.date | None = None, user: User = Depends(require("dunning.read")), db: Session = Depends(get_db)):
    ids = None
    if scoped(user):
        ids = [c.id for c in db.execute(select(Customer).where(Customer.salesperson_id == user.id)).scalars()] or [0]
    return out(dunning.proposals(db, as_of, ids))


@router.get("/dunning/meta", tags=["Recouvrement"])
def meta(user: User = Depends(get_current_user)):
    return out({"action_types": dunning.ACTION_TYPES, "result_codes": dunning.RESULT_CODES,
                "channels": ["LETTRE", "EMAIL", "TELEPHONE", "SMS", "VISITE", "HUISSIER", "AVOCAT"]})


@router.get("/dunning/actions", tags=["Recouvrement"])
def actions(customer_id: int | None = None, due_only: bool = False, limit: int = 300, user: User = Depends(require("dunning.read")),
            db: Session = Depends(get_db)):
    q = select(DunningAction).order_by(DunningAction.action_date.desc(), DunningAction.id.desc())
    if customer_id:
        check_customer_access(db, user, customer_id)
        q = q.where(DunningAction.customer_id == customer_id)
    elif scoped(user):
        q = q.join(Customer, Customer.id == DunningAction.customer_id).where(Customer.salesperson_id == user.id)
    if due_only:
        q = q.where(DunningAction.next_action_date <= dt.date.today())
    return out([dunning.action_dict(db, a) for a in db.execute(q.limit(limit)).scalars()])


@router.post("/dunning/preview", tags=["Recouvrement"])
def preview(body: PreviewIn, user: User = Depends(require("dunning.read")), db: Session = Depends(get_db)):
    check_customer_access(db, user, body.customer_id)
    return out(dunning.preview(db, user, body.customer_id, body.template_id, body.invoice_ids))


@router.post("/dunning/actions", tags=["Recouvrement"])
def create_action(body: DunningActionIn, request: Request, user: User = Depends(require("dunning.write")), db: Session = Depends(get_db)):
    check_customer_access(db, user, body.customer_id)
    a = dunning.create_action(db, user, body.model_dump())
    audit.log(db, user, "DUNNING_ACTION", "customer", body.customer_id, {"action": a.id, "type": a.action_type, "result": a.result_code,
                                                                         "invoices": body.invoice_ids}, ip(request))
    db.commit()
    return out(dunning.action_dict(db, a), 201)


# ------------------------------------------------------------------ risque
@router.get("/risk/customers/{cid}", tags=["Risque"])
def risk_customer(cid: int, user: User = Depends(require("risk.read")), db: Session = Depends(get_db)):
    c = check_customer_access(db, user, cid)
    save = has_permission(user.role, "risk.compute")
    res = risk.compute(db, c, save=save)
    if save:
        db.commit()
    return out(res)


@router.post("/risk/recompute", tags=["Risque"])
def risk_all(request: Request, user: User = Depends(require("risk.compute")), db: Session = Depends(get_db)):
    res = risk.compute_all(db)
    audit.log(db, user, "RISK_RECOMPUTED", "customer", None, {"count": len(res)}, ip(request))
    db.commit()
    return out({"count": len(res), "degraded": [r for r in res if r["degraded"]],
                "distribution": {k: sum(1 for r in res if r["risk_class"] == k) for k in risk.CLASSES}})


@router.get("/risk/overview", tags=["Risque"])
def risk_overview(user: User = Depends(require("risk.read")), db: Session = Depends(get_db)):
    from ..services.ledger import customer_exposure
    q = select(Customer).where(Customer.status != "ARCHIVE").order_by(Customer.risk_score.desc().nullslast())
    if scoped(user):
        q = q.where(Customer.salesperson_id == user.id)
    rows = []
    for c in db.execute(q).scalars():
        e = customer_exposure(db, c.id)
        if e["open_tnd"] == 0 and not c.risk_score:
            continue
        rows.append({"customer_id": c.id, "code": c.code, "name": c.legal_name, "risk_score": c.risk_score, "risk_class": c.risk_class,
                     "risk_computed_at": c.risk_computed_at, **e})
    return out(rows)


# ------------------------------------------------------------------ provisions
def _campaign_dict(db, c: ProvisionCampaign, lines=True):
    d = {"id": c.id, "as_of": c.as_of, "method": c.method, "status": c.status, "notes": c.notes, "total_amount_tnd": c.total_amount_tnd,
         "created_by": db.get(User, c.created_by).full_name if c.created_by else None, "created_at": c.created_at,
         "validated_by": db.get(User, c.validated_by).full_name if c.validated_by else None, "validated_at": c.validated_at,
         "dotation": sum((l.movement_tnd for l in c.lines if l.movement_tnd > 0), 0),
         "reprise": sum((-l.movement_tnd for l in c.lines if l.movement_tnd < 0), 0), "line_count": len(c.lines)}
    if lines:
        d["lines"] = []
        for l in sorted(c.lines, key=lambda x: (-x.amount_tnd, x.id)):
            inv = db.get(Invoice, l.invoice_id)
            d["lines"].append({"id": l.id, "invoice_id": l.invoice_id, "invoice_number": inv.number, "customer_code": inv.customer.code,
                               "customer_name": inv.customer.legal_name, "classification": inv.classification, "bucket": l.bucket,
                               "days_overdue": l.days_overdue, "outstanding_tnd": l.outstanding_tnd, "base_tnd": l.base_tnd,
                               "rate": l.rate, "suggested_rate": l.suggested_rate, "amount_tnd": l.amount_tnd,
                               "previous_amount_tnd": l.previous_amount_tnd, "movement_tnd": l.movement_tnd,
                               "justification": l.justification, "fiscal_deductible": l.fiscal_deductible, "fiscal_note": l.fiscal_note})
    return d


@router.get("/provisions/campaigns", tags=["Provisions"])
def campaigns(user: User = Depends(require("provisions.read")), db: Session = Depends(get_db)):
    rows = db.execute(select(ProvisionCampaign).order_by(ProvisionCampaign.id.desc())).scalars()
    return out([_campaign_dict(db, c, False) for c in rows])


@router.post("/provisions/campaigns", tags=["Provisions"])
def propose(body: ProvisionProposeIn, request: Request, user: User = Depends(require("provisions.propose")), db: Session = Depends(get_db)):
    c = provisions.propose(db, user, body.as_of, body.method, body.notes)
    audit.log(db, user, "PROVISION_PROPOSED", "provision", c.id, {"method": c.method, "as_of": c.as_of, "total": str(c.total_amount_tnd)}, ip(request))
    db.commit()
    return out(_campaign_dict(db, c), 201)


@router.get("/provisions/campaigns/{cid}", tags=["Provisions"])
def campaign(cid: int, user: User = Depends(require("provisions.read")), db: Session = Depends(get_db)):
    c = db.get(ProvisionCampaign, cid)
    if not c:
        raise HTTPException(404, "Campagne introuvable")
    return out(_campaign_dict(db, c))


@router.put("/provisions/lines/{lid}", tags=["Provisions"])
def update_line(lid: int, body: ProvisionLineIn, request: Request, user: User = Depends(require("provisions.propose")), db: Session = Depends(get_db)):
    ln = db.get(Provision, lid)
    if not ln:
        raise HTTPException(404, "Ligne introuvable")
    old = {"rate": str(ln.rate), "amount": str(ln.amount_tnd)}
    provisions.update_line(db, ln, body.rate, body.justification, body.fiscal_deductible)
    audit.log(db, user, "PROVISION_LINE_UPDATED", "provision", ln.campaign_id, {"line": lid, "old": old, "new_rate": str(body.rate),
                                                                                 "justification": body.justification}, ip(request))
    db.commit()
    return out(_campaign_dict(db, ln.campaign))


@router.post("/provisions/campaigns/{cid}/decide", tags=["Provisions"])
def decide_campaign(cid: int, body: DecisionIn, request: Request, user: User = Depends(require("provisions.validate")), db: Session = Depends(get_db)):
    c = db.get(ProvisionCampaign, cid)
    if not c:
        raise HTTPException(404, "Campagne introuvable")
    provisions.validate(db, user, c, body.approve, body.comment)
    audit.log(db, user, "PROVISION_" + c.status, "provision", c.id, {"total": str(c.total_amount_tnd), "comment": body.comment}, ip(request))
    db.commit()
    return out(_campaign_dict(db, c))


@router.get("/provisions/loss-rates", tags=["Provisions"])
def loss_rates(user: User = Depends(require("provisions.read")), db: Session = Depends(get_db)):
    return out(provisions.observed_loss_rates(db))


# ------------------------------------------------------------------ approbations
def _appr_dict(db, r: ApprovalRequest):
    return {"id": r.id, "kind": r.kind, "kind_label": approvals.KINDS.get(r.kind), "entity_type": r.entity_type, "entity_id": r.entity_id,
            "payload": r.payload, "reason": r.reason, "status": r.status, "requested_by": db.get(User, r.requested_by).full_name,
            "requested_by_id": r.requested_by, "requested_at": r.requested_at,
            "decided_by": db.get(User, r.decided_by).full_name if r.decided_by else None, "decided_at": r.decided_at,
            "decision_comment": r.decision_comment}


@router.get("/approvals", tags=["Contrôle interne"])
def list_approvals(status: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = select(ApprovalRequest).order_by(ApprovalRequest.id.desc())
    if status:
        q = q.where(ApprovalRequest.status == status)
    if not has_permission(user.role, "approvals.decide"):
        q = q.where(ApprovalRequest.requested_by == user.id)
    return out([_appr_dict(db, r) for r in db.execute(q.limit(300)).scalars()])


@router.post("/approvals", tags=["Contrôle interne"])
def create_approval(body: ApprovalIn, user: User = Depends(require("customers.write")), db: Session = Depends(get_db)):
    if body.entity_type == "customer":
        check_customer_access(db, user, body.entity_id)
    r = approvals.request(db, user, body.kind, body.entity_type, body.entity_id, body.payload, body.reason)
    db.commit()
    return out(_appr_dict(db, r), 201)


@router.post("/approvals/{rid}/decide", tags=["Contrôle interne"])
def decide(rid: int, body: DecisionIn, user: User = Depends(require("approvals.decide")), db: Session = Depends(get_db)):
    r = db.get(ApprovalRequest, rid)
    if not r:
        raise HTTPException(404, "Demande introuvable")
    approvals.decide(db, user, r, body.approve, body.comment)
    db.commit()
    return out(_appr_dict(db, r))
