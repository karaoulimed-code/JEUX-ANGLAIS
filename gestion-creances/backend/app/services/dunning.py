"""Échéancier et recouvrement : propositions de relance, historique, modèles."""
import datetime as dt
from collections import defaultdict
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..money import ZERO
from ..models import (Customer, DunningAction, DunningActionInvoice, DunningLevel, DunningTemplate, Installment, Invoice, User)
from .ledger import open_items
from .params import get_param

ACTION_TYPES = {
    "RELANCE_PREVENTIVE": "Rappel avant échéance", "RELANCE_1": "Première relance amiable", "RELANCE_2": "Deuxième relance",
    "MISE_EN_DEMEURE": "Mise en demeure", "TRANSMISSION_JURIDIQUE": "Transmission au service juridique",
    "CONTENTIEUX": "Suivi du contentieux", "APPEL": "Appel téléphonique", "VISITE": "Visite", "AUTRE": "Autre action",
}
RESULT_CODES = {
    "PROMESSE": "Promesse de paiement", "SANS_REPONSE": "Sans réponse", "CONTESTATION": "Contestation / litige",
    "PAIEMENT_PARTIEL": "Paiement partiel", "PAYE": "Payé", "INJOIGNABLE": "Injoignable", "ECHEANCIER": "Échéancier négocié",
    "EN_COURS": "En cours", "AUTRE": "Autre",
}


def _fmt(v: Decimal) -> str:
    s = f"{v:,.3f}".replace(",", " ").replace(".", ",")
    return s + " TND"


def render(db: Session, tpl: DunningTemplate, cust: Customer, invoices: list[dict], user: User | None) -> tuple[str, str]:
    company = get_param(db, "company") or {}
    total = sum((i["remaining_tnd"] for i in invoices), ZERO)
    lines = "\n".join(f"  - Facture {i['number']} du {i['issue_date']:%d/%m/%Y}, échue le {i['due_date']:%d/%m/%Y} : "
                      f"{_fmt(i['remaining_tnd'])} ({max(0, i['days_overdue'])} jours de retard)" for i in invoices)
    values = {
        "client": cust.legal_name, "code_client": cust.code, "contact": cust.contact_name or "Madame, Monsieur",
        "date": dt.date.today().strftime("%d/%m/%Y"), "montant_du": _fmt(total), "liste_factures": lines,
        "nombre_factures": str(len(invoices)), "societe": company.get("name", ""), "adresse_societe": company.get("address", ""),
        "telephone_societe": company.get("phone", ""), "responsable": user.full_name if user else "",
        "jours_retard": str(max([i["days_overdue"] for i in invoices] or [0])), "adresse_client": cust.address or "",
    }

    class SafeDict(dict):
        def __missing__(self, k):
            return "{" + k + "}"
    return (tpl.subject or "").format_map(SafeDict(values)), tpl.body.format_map(SafeDict(values))


def proposals(db: Session, as_of: dt.date | None = None, customer_ids: list[int] | None = None) -> dict:
    """Clients à relancer, niveau recommandé et créances concernées."""
    as_of = as_of or dt.date.today()
    levels = list(db.execute(select(DunningLevel).where(DunningLevel.active.is_(True)).order_by(DunningLevel.level)).scalars())
    items = [i for i in open_items(db, as_of, customer_ids) if i["classification"] != "IRRECOUVRABLE"]
    by_c: dict[int, list] = defaultdict(list)
    for i in items:
        by_c[i["customer_id"]].append(i)
    custs = {c.id: c for c in db.execute(select(Customer).where(Customer.id.in_(list(by_c) or [0]))).scalars()}
    prev_days = int(get_param(db, "dunning.preventive_days") or 7)
    overdue_out, upcoming_out = [], []
    for cid, its in by_c.items():
        cust = custs[cid]
        od = [i for i in its if i["days_overdue"] > 0]
        soon = [i for i in its if -prev_days <= i["days_overdue"] <= 0]
        if soon:
            upcoming_out.append({"customer_id": cid, "code": cust.code, "name": cust.legal_name,
                                 "amount": sum((i["remaining_tnd"] for i in soon), ZERO),
                                 "next_due": min(i["due_date"] for i in soon), "invoices": soon})
        if not od:
            continue
        oldest_due = min(i["due_date"] for i in od)
        max_days = max(i["days_overdue"] for i in od)
        amount = sum((i["remaining_tnd"] for i in od), ZERO)
        acts = list(db.execute(select(DunningAction).where(DunningAction.customer_id == cid, DunningAction.action_date >= oldest_due)
                               .order_by(DunningAction.action_date.desc(), DunningAction.id.desc())).scalars())
        last_level = 0
        for a in acts:
            if a.level_id:
                last_level = max(last_level, db.get(DunningLevel, a.level_id).level)
        last = acts[0] if acts else None
        promise = next((a for a in acts if a.promised_date and a.promised_date >= as_of), None)
        # Escalade progressive : on propose le niveau suivant le dernier niveau atteint,
        # si son seuil de retard est atteint et si le délai minimal depuis la dernière
        # action est écoulé (on ne passe pas d'une absence de relance au contentieux).
        recommended = None
        gap = int(get_param(db, "dunning.min_days_between") or 0)
        too_soon = bool(last and (as_of - last.action_date).days < gap)
        nxt = next((lv for lv in levels if lv.level > last_level), None)
        if nxt and nxt.days_after_due <= max_days and amount >= nxt.min_amount and not too_soon:
            recommended = nxt
        due_followup = bool(last and last.next_action_date and last.next_action_date <= as_of)
        overdue_out.append({
            "customer_id": cid, "code": cust.code, "name": cust.legal_name, "risk_class": cust.risk_class,
            "in_litigation": cust.in_litigation, "amount_overdue": amount, "max_days_overdue": max_days,
            "invoice_count": len(od), "last_action": {"date": last.action_date, "type": last.action_type, "result": last.result_code,
                                                      "next_action_date": last.next_action_date} if last else None,
            "last_level": last_level, "promise": {"date": promise.promised_date, "amount": promise.promised_amount} if promise else None,
            "recommended_level": {"id": recommended.id, "level": recommended.level, "code": recommended.code, "label": recommended.label,
                                  "template_id": recommended.template_id} if recommended else None,
            "followup_due": due_followup, "invoices": od,
            "needs_action": bool((recommended and not promise) or due_followup),
        })
    overdue_out.sort(key=lambda x: (-int(x["needs_action"]), -x["max_days_overdue"], -x["amount_overdue"]))
    upcoming_out.sort(key=lambda x: x["next_due"])
    return {"as_of": as_of, "overdue": overdue_out, "upcoming": upcoming_out}


def preview(db: Session, user: User, customer_id: int, template_id: int, invoice_ids: list[int] | None) -> dict:
    cust = db.get(Customer, customer_id)
    tpl = db.get(DunningTemplate, template_id)
    if not cust or not tpl:
        raise HTTPException(404, "Client ou modèle introuvable")
    its = [i for i in open_items(db, None, [customer_id]) if (not invoice_ids or i["invoice_id"] in invoice_ids)]
    if not invoice_ids:
        its = [i for i in its if i["days_overdue"] > 0] or its
    subject, body = render(db, tpl, cust, its, user)
    return {"subject": subject, "body": body, "channel": tpl.channel}


def create_action(db: Session, user: User, data: dict) -> DunningAction:
    cust = db.get(Customer, data["customer_id"])
    if not cust:
        raise HTTPException(404, "Client introuvable")
    if data["action_type"] not in ACTION_TYPES:
        raise HTTPException(400, "Type d'action inconnu")
    if data.get("result_code") and data["result_code"] not in RESULT_CODES:
        raise HTTPException(400, "Résultat inconnu")
    inv_ids = data.get("invoice_ids") or []
    its = {i["invoice_id"]: i for i in open_items(db, None, [cust.id])}
    a = DunningAction(customer_id=cust.id, level_id=data.get("level_id"), action_type=data["action_type"],
                      action_date=data.get("action_date") or dt.date.today(), channel=data.get("channel") or "LETTRE",
                      responsible_id=data.get("responsible_id") or user.id, result_code=data.get("result_code"),
                      result=data.get("result"), promised_date=data.get("promised_date"), promised_amount=data.get("promised_amount"),
                      next_action=data.get("next_action"), next_action_date=data.get("next_action_date"),
                      comments=data.get("comments"), rendered_subject=data.get("rendered_subject"),
                      rendered_text=data.get("rendered_text"), created_by=user.id)
    total = ZERO
    for iid in inv_ids:
        inv = db.get(Invoice, iid)
        if not inv or inv.customer_id != cust.id:
            raise HTTPException(400, f"Facture {iid} invalide pour ce client")
        bal = its[iid]["remaining_tnd"] if iid in its else ZERO
        total += bal
        a.invoices.append(DunningActionInvoice(invoice_id=iid, balance_at_action=bal))
    a.amount_due_tnd = total
    if a.level_id:
        lv = db.get(DunningLevel, a.level_id)
        if lv and lv.escalate_to_legal:
            cust.in_litigation = True
    if a.action_type in ("TRANSMISSION_JURIDIQUE", "CONTENTIEUX"):
        cust.in_litigation = True
    db.add(a)
    db.flush()
    return a


def action_dict(db: Session, a: DunningAction) -> dict:
    cust = db.get(Customer, a.customer_id)
    resp = db.get(User, a.responsible_id) if a.responsible_id else None
    lv = db.get(DunningLevel, a.level_id) if a.level_id else None
    return {
        "id": a.id, "customer_id": a.customer_id, "customer_code": cust.code, "customer_name": cust.legal_name,
        "level": lv.level if lv else None, "level_label": lv.label if lv else None,
        "action_type": a.action_type, "action_label": ACTION_TYPES.get(a.action_type, a.action_type),
        "action_date": a.action_date, "channel": a.channel, "responsible": resp.full_name if resp else None,
        "result_code": a.result_code, "result_label": RESULT_CODES.get(a.result_code or "", None), "result": a.result,
        "promised_date": a.promised_date, "promised_amount": a.promised_amount, "next_action": a.next_action,
        "next_action_date": a.next_action_date, "comments": a.comments, "amount_due_tnd": a.amount_due_tnd,
        "rendered_subject": a.rendered_subject, "rendered_text": a.rendered_text,
        "invoices": [{"invoice_id": x.invoice_id, "number": db.get(Invoice, x.invoice_id).number, "balance": x.balance_at_action} for x in a.invoices],
        "created_at": a.created_at,
    }
