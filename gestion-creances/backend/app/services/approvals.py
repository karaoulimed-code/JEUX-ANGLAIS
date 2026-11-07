"""Validation « à quatre yeux » des opérations sensibles : le demandeur ne peut
jamais approuver sa propre demande."""
import datetime as dt

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..money import D, q3
from ..models import ApprovalRequest, Customer, Invoice, Payment, User, now_utc
from .. import audit

KINDS = {
    "CREDIT_LIMIT": "Modification du plafond de crédit",
    "WRITE_OFF": "Passage en perte (créance irrécouvrable)",
    "PAYMENT_CANCEL": "Annulation d'un règlement",
    "CUSTOMER_BLOCK": "Blocage / déblocage d'un client",
}


def request(db: Session, user: User, kind: str, entity_type: str, entity_id: int, payload: dict, reason: str) -> ApprovalRequest:
    if kind not in KINDS:
        raise HTTPException(400, "Type de demande inconnu")
    if not reason or len(reason.strip()) < 10:
        raise HTTPException(400, "Motif détaillé obligatoire (10 caractères minimum)")
    from sqlalchemy import select
    dup = db.execute(select(ApprovalRequest).where(ApprovalRequest.kind == kind, ApprovalRequest.entity_type == entity_type,
                                                   ApprovalRequest.entity_id == entity_id, ApprovalRequest.status == "EN_ATTENTE")).first()
    if dup:
        raise HTTPException(409, "Une demande identique est déjà en attente")
    if kind == "WRITE_OFF":
        inv = db.get(Invoice, entity_id)
        if not inv or inv.doc_type != "FACTURE" or inv.lifecycle != "VALIDEE" or inv.balance <= 0:
            raise HTTPException(409, "Facture non éligible au passage en perte")
        payload = {**payload, "amount": str(inv.balance)}
    r = ApprovalRequest(kind=kind, entity_type=entity_type, entity_id=entity_id, payload=payload, reason=reason, requested_by=user.id)
    db.add(r)
    db.flush()
    audit.log(db, user, "APPROVAL_REQUEST", entity_type, entity_id, {"kind": kind, "payload": payload, "reason": reason})
    return r


def decide(db: Session, user: User, r: ApprovalRequest, approve: bool, comment: str | None) -> None:
    from . import payments, provisions
    if r.status != "EN_ATTENTE":
        raise HTTPException(409, "Demande déjà traitée")
    if r.requested_by == user.id:
        raise HTTPException(403, "Séparation des fonctions : vous ne pouvez pas approuver votre propre demande")
    r.status = "APPROUVEE" if approve else "REJETEE"
    r.decided_by = user.id
    r.decided_at = now_utc()
    r.decision_comment = comment
    if approve:
        if r.kind == "CREDIT_LIMIT":
            c = db.get(Customer, r.entity_id)
            old = {"credit_limit": str(c.credit_limit), "max_exposure": str(c.max_exposure)}
            if "credit_limit" in r.payload:
                c.credit_limit = q3(r.payload["credit_limit"])
            if "max_exposure" in r.payload:
                c.max_exposure = q3(r.payload["max_exposure"])
            audit.log(db, user, "CREDIT_LIMIT_CHANGED", "customer", c.id, {"old": old, "new": r.payload, "approval": r.id})
        elif r.kind == "CUSTOMER_BLOCK":
            c = db.get(Customer, r.entity_id)
            c.status = r.payload.get("status", "BLOQUE")
            audit.log(db, user, "CUSTOMER_STATUS_CHANGED", "customer", c.id, {"status": c.status, "approval": r.id})
        elif r.kind == "WRITE_OFF":
            inv = db.get(Invoice, r.entity_id)
            if inv.balance <= 0:
                raise HTTPException(409, "La facture a été soldée entre-temps")
            prov = provisions.current_provisions(db, "NCT").get(inv.id, D(0))
            kind = r.payload.get("kind", "PASSAGE_PERTE")
            adj = payments.create_adjustment(db, user, inv, kind, inv.balance, r.reason, dt.date.today(), r.id, prov)
            inv.classification = "IRRECOUVRABLE"
            inv.classification_reason = r.reason
            inv.classified_at = now_utc()
            audit.log(db, user, "WRITE_OFF", "invoice", inv.id, {"adjustment": adj.number, "amount": str(adj.amount), "approval": r.id,
                                                                 "provision_reversed": str(prov)})
        elif r.kind == "PAYMENT_CANCEL":
            p = db.get(Payment, r.entity_id)
            payments.cancel_payment(db, user, p, r.reason)
            audit.log(db, user, "PAYMENT_CANCELLED", "payment", p.id, {"approval": r.id, "reason": r.reason})
    audit.log(db, user, "APPROVAL_" + r.status, r.entity_type, r.entity_id, {"kind": r.kind, "comment": comment, "request": r.id})
