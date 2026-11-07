"""Catalogue des états : chaque état renvoie titre, colonnes typées, lignes et totaux,
puis est rendu en JSON, Excel, PDF ou CSV par le même moteur."""
import datetime as dt
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..money import ZERO
from ..models import (Customer, DunningAction, Invoice, Payment, Provision, ProvisionCampaign)
from . import dunning as dunning_svc
from .forecast import cash_forecast
from .invoices import SETTLEMENT_LABELS, settlement_status
from .ledger import aging, customer_exposure, ledger, ledger_balances, open_items, unallocated_credits

A = "amount"


def _col(key, label, kind=None, width=16):
    return {"key": key, "label": label, "kind": kind, "width": width}


def _sum(rows, keys):
    return {k: sum((r.get(k) or ZERO for r in rows), ZERO) for k in keys}


def r_grand_livre(db, p):
    cid = p.get("customer_id")
    if not cid:
        raise HTTPException(400, "customer_id requis pour le grand livre")
    c = db.get(Customer, int(cid))
    lg = ledger(db, c.id, p.get("date_from"), p.get("date_to"))
    rows = [{"date": None, "piece": "", "label": "Solde d'ouverture", "debit": None, "credit": None, "balance": lg["opening_balance"]}] + lg["rows"]
    return {"title": f"Grand livre auxiliaire – {c.code} {c.legal_name}",
            "columns": [_col("date", "Date", "date", 12), _col("piece", "Pièce", None, 18), _col("label", "Libellé", None, 45),
                        _col("due_date", "Échéance", "date", 12), _col("debit", "Débit", A), _col("credit", "Crédit", A), _col("balance", "Solde", A)],
            "rows": rows, "totals": {"label": "Totaux", "debit": lg["total_debit"], "credit": lg["total_credit"], "balance": lg["closing_balance"]}}


def r_balance_auxiliaire(db, p):
    bal = ledger_balances(db, p.get("date_to"), p.get("date_from"))
    custs = {c.id: c for c in db.execute(select(Customer)).scalars()}
    rows = []
    for cid, b in sorted(bal.items(), key=lambda kv: custs[kv[0]].code):
        c = custs[cid]
        rows.append({"code": c.code, "name": c.legal_name, "opening": b["opening"], "debit": b["debit"], "credit": b["credit"],
                     "closing_debit": b["closing"] if b["closing"] > 0 else ZERO, "closing_credit": -b["closing"] if b["closing"] < 0 else ZERO})
    t = _sum(rows, ["opening", "debit", "credit", "closing_debit", "closing_credit"])
    t["name"] = "TOTAL"
    return {"title": "Balance auxiliaire clients",
            "columns": [_col("code", "Code", None, 12), _col("name", "Client", None, 35), _col("opening", "Solde ouverture", A),
                        _col("debit", "Mouvements débit", A), _col("credit", "Mouvements crédit", A),
                        _col("closing_debit", "Solde débiteur", A), _col("closing_credit", "Solde créditeur", A)],
            "rows": rows, "totals": t}


def _invoice_rows(db, q, as_of):
    rows = []
    for inv in db.execute(q).scalars():
        st = settlement_status(inv, as_of)
        rows.append({"number": inv.number, "customer": f"{inv.customer.code} {inv.customer.legal_name}", "issue_date": inv.issue_date,
                     "due_date": inv.due_date, "currency": inv.currency, "total_ttc": inv.total_ttc, "paid": inv.paid_amount,
                     "balance": inv.balance, "balance_tnd": inv.balance * inv.exchange_rate,
                     "days": max(0, (as_of - inv.due_date).days), "status": SETTLEMENT_LABELS[st], "classification": inv.classification})
    return rows


INV_COLS = [_col("number", "N° facture", None, 16), _col("customer", "Client", None, 32), _col("issue_date", "Date", "date", 11),
            _col("due_date", "Échéance", "date", 11), _col("currency", "Dev.", None, 6), _col("total_ttc", "TTC", A),
            _col("paid", "Réglé", A), _col("balance", "Reste dû", A), _col("days", "Retard (j)", "int", 9), _col("status", "Statut", None, 16)]


def r_etat_creances(db, p):
    as_of = p.get("date_to") or dt.date.today()
    q = (select(Invoice).where(Invoice.lifecycle == "VALIDEE", Invoice.doc_type == "FACTURE", Invoice.balance > 0)
         .order_by(Invoice.customer_id, Invoice.due_date))
    if p.get("customer_id"):
        q = q.where(Invoice.customer_id == int(p["customer_id"]))
    rows = _invoice_rows(db, q, as_of)
    return {"title": "État détaillé des créances", "columns": INV_COLS, "rows": rows, "totals": {**_sum(rows, ["balance_tnd"]), "customer": "TOTAL TND", "balance": _sum(rows, ["balance_tnd"])["balance_tnd"]}}


def r_factures_impayees(db, p):
    as_of = p.get("date_to") or dt.date.today()
    q = (select(Invoice).join(Invoice.installments).where(Invoice.lifecycle == "VALIDEE", Invoice.doc_type == "FACTURE", Invoice.balance > 0)
         .where(Invoice.due_date < as_of).distinct().order_by(Invoice.due_date))
    rows = [r for r in _invoice_rows(db, q, as_of) if r["days"] > 0]
    s = _sum(rows, ["balance_tnd"])["balance_tnd"]
    return {"title": "État des factures impayées (échues)", "columns": INV_COLS, "rows": rows, "totals": {"customer": "TOTAL TND", "balance": s}}


def r_creances_douteuses(db, p):
    as_of = p.get("date_to") or dt.date.today()
    q = (select(Invoice).where(Invoice.doc_type == "FACTURE", Invoice.lifecycle == "VALIDEE",
                               Invoice.classification.in_(["DOUTEUSE", "LITIGIEUSE", "IRRECOUVRABLE"])).order_by(Invoice.classification, Invoice.due_date))
    rows = _invoice_rows(db, q, as_of)
    for r, inv in zip(rows, db.execute(q).scalars()):
        r["reason"] = inv.classification_reason
    cols = INV_COLS[:-1] + [_col("classification", "Classement", None, 14), _col("reason", "Justification", None, 40)]
    return {"title": "État des créances douteuses, litigieuses et irrécouvrables", "columns": cols, "rows": rows,
            "totals": {"customer": "TOTAL TND", "balance": _sum(rows, ["balance_tnd"])["balance_tnd"]}}


def r_balance_agee(db, p):
    ag = aging(db, p.get("date_to"), [int(p["customer_id"])] if p.get("customer_id") else None, p.get("currency"),
               p.get("group_by") or "customer", {k: p.get(k) for k in ("group_code", "category_code", "zone_code", "risk_class", "salesperson_id")})
    cols = [_col("code", "Code", None, 12), _col("name", "Client / regroupement", None, 32)] + \
           [_col(b["code"], b["label"], A, 14) for b in ag["buckets"]] + \
           [_col("total", "Total", A), _col("unallocated", "Crédits non affectés", A), _col("net", "Solde net", A)]
    t = dict(ag["totals"])
    t["name"] = "TOTAL"
    return {"title": f"Balance âgée clients au {ag['as_of']:%d/%m/%Y} ({ag['currency']})", "columns": cols, "rows": ag["rows"], "totals": t}


def _journal(db, p, doc_types):
    q = select(Invoice).where(Invoice.lifecycle == "VALIDEE", Invoice.doc_type.in_(doc_types)).order_by(Invoice.issue_date, Invoice.number)
    if p.get("date_from"):
        q = q.where(Invoice.issue_date >= p["date_from"])
    if p.get("date_to"):
        q = q.where(Invoice.issue_date <= p["date_to"])
    rows = []
    for inv in db.execute(q).scalars():
        s = -1 if inv.doc_type == "AVOIR" else 1
        rate = inv.exchange_rate
        rows.append({"date": inv.issue_date, "number": inv.number, "type": inv.doc_type.capitalize(),
                     "customer": f"{inv.customer.code} {inv.customer.legal_name}", "tax_id": inv.customer.tax_id,
                     "ht": s * inv.total_ht * rate, "vat": s * inv.total_vat * rate, "other": s * inv.total_other_taxes * rate,
                     "ttc": s * inv.total_ttc_tnd})
    return rows


def r_journal_ventes(db, p):
    rows = _journal(db, p, ["FACTURE", "AVOIR"])
    t = _sum(rows, ["ht", "vat", "other", "ttc"])
    t["customer"] = "TOTAL"
    return {"title": "Journal des ventes (factures et avoirs, en TND)",
            "columns": [_col("date", "Date", "date", 11), _col("number", "N°", None, 16), _col("type", "Type", None, 9),
                        _col("customer", "Client", None, 32), _col("tax_id", "Matricule fiscal", None, 16), _col("ht", "HT", A),
                        _col("vat", "TVA", A), _col("other", "Timbre / autres", A), _col("ttc", "TTC", A)], "rows": rows, "totals": t}


def r_journal_encaissements(db, p):
    q = select(Payment).order_by(Payment.receipt_date, Payment.number)
    if p.get("date_from"):
        q = q.where(Payment.receipt_date >= p["date_from"])
    if p.get("date_to"):
        q = q.where(Payment.receipt_date <= p["date_to"])
    rows = [{"date": x.receipt_date, "number": x.number, "customer": f"{x.customer.code} {x.customer.legal_name}", "method": x.method.label,
             "reference": x.reference, "status": x.status, "amount": x.amount, "currency": x.currency, "amount_tnd": x.amount_tnd,
             "allocated": x.allocated_amount} for x in db.execute(q).scalars()]
    valid = [r for r in rows if r["status"] not in ("REJETE", "ANNULE")]
    return {"title": "Journal des encaissements",
            "columns": [_col("date", "Date", "date", 11), _col("number", "N°", None, 15), _col("customer", "Client", None, 30),
                        _col("method", "Moyen", None, 14), _col("reference", "Référence", None, 14), _col("status", "Statut", None, 13),
                        _col("amount", "Montant", A), _col("currency", "Dev.", None, 6), _col("amount_tnd", "Montant TND", A), _col("allocated", "Affecté", A)],
            "rows": rows, "totals": {"customer": "TOTAL (hors rejetés/annulés)", "amount_tnd": _sum(valid, ["amount_tnd"])["amount_tnd"]}}


def r_provisions(db, p):
    method = p.get("method") or "NCT"
    q = (select(Provision, ProvisionCampaign).join(ProvisionCampaign).where(ProvisionCampaign.method == method,
                                                                          ProvisionCampaign.status == "VALIDEE")
         .order_by(ProvisionCampaign.as_of.desc(), ProvisionCampaign.id.desc()))
    rows = []
    first = None
    for pr, c in db.execute(q):
        if first is None:
            first = c.id
        if c.id != first:
            break
        inv = db.get(Invoice, pr.invoice_id)
        rows.append({"number": inv.number, "customer": f"{inv.customer.code} {inv.customer.legal_name}", "days": pr.days_overdue,
                     "outstanding": pr.outstanding_tnd, "base": pr.base_tnd, "rate": pr.rate, "amount": pr.amount_tnd,
                     "previous": pr.previous_amount_tnd, "movement": pr.movement_tnd, "justification": pr.justification,
                     "fiscal": "Oui" if pr.fiscal_deductible else "À vérifier"})
    t = _sum(rows, ["outstanding", "base", "amount", "previous", "movement"])
    t["customer"] = "TOTAL"
    return {"title": f"État des provisions ({method}) – dernière campagne validée",
            "columns": [_col("number", "Facture", None, 15), _col("customer", "Client", None, 28), _col("days", "Retard (j)", "int", 9),
                        _col("outstanding", "Encours TTC", A), _col("base", "Base", A), _col("rate", "Taux %", "pct", 8),
                        _col("amount", "Provision", A), _col("previous", "Antérieure", A), _col("movement", "Dotation / (reprise)", A),
                        _col("justification", "Justification", None, 30), _col("fiscal", "Déductible", None, 10)], "rows": rows, "totals": t}


def r_depassements(db, p):
    rows = []
    for c in db.execute(select(Customer).where(Customer.status != "ARCHIVE")).scalars():
        e = customer_exposure(db, c.id)
        if e["over_limit"] or e["over_exposure"]:
            rows.append({"code": c.code, "name": c.legal_name, "limit": c.credit_limit, "open": e["open_tnd"],
                         "overrun": e["open_tnd"] - c.credit_limit if c.credit_limit else None, "max_exposure": c.max_exposure,
                         "exposure": e["exposure_tnd"], "overdue": e["overdue_tnd"], "risk": c.risk_class})
    return {"title": "État des dépassements de plafond et d'encours",
            "columns": [_col("code", "Code", None, 12), _col("name", "Client", None, 32), _col("limit", "Plafond", A), _col("open", "Créances ouvertes", A),
                        _col("overrun", "Dépassement", A), _col("max_exposure", "Encours max", A), _col("exposure", "Encours total", A),
                        _col("overdue", "Dont échu", A), _col("risk", "Risque", None, 10)], "rows": rows, "totals": None}


def r_prevision(db, p):
    f = cash_forecast(db, p.get("date_to"))
    rows = [{"period": f"{w['week_start']:%d/%m} – {w['week_end']:%d/%m/%Y}", "invoices": w["invoices"], "instruments": w["instruments"],
             "total": w["total"], "cumulative": w["cumulative"], "contractual": w["contractual"]} for w in f["weeks"]]
    t = _sum(rows, ["invoices", "instruments", "total", "contractual"])
    t["period"] = "TOTAL 13 semaines"
    return {"title": "Prévision des encaissements (13 semaines)", "subtitle": f["method"],
            "columns": [_col("period", "Semaine", None, 24), _col("invoices", "Factures (prévision)", A), _col("instruments", "Chèques / effets", A),
                        _col("total", "Total prévu", A), _col("cumulative", "Cumul", A), _col("contractual", "Échéances contractuelles", A)],
            "rows": rows, "totals": t}


def r_relances(db, p):
    q = select(DunningAction).order_by(DunningAction.action_date.desc(), DunningAction.id.desc())
    if p.get("customer_id"):
        q = q.where(DunningAction.customer_id == int(p["customer_id"]))
    if p.get("date_from"):
        q = q.where(DunningAction.action_date >= p["date_from"])
    if p.get("date_to"):
        q = q.where(DunningAction.action_date <= p["date_to"])
    rows = []
    for a in db.execute(q).scalars():
        d = dunning_svc.action_dict(db, a)
        rows.append({**d, "customer": f"{d['customer_code']} {d['customer_name']}", "invoices_txt": ", ".join(i["number"] for i in d["invoices"])})
    return {"title": "Historique des relances et actions de recouvrement",
            "columns": [_col("action_date", "Date", "date", 11), _col("customer", "Client", None, 28), _col("action_label", "Action", None, 22),
                        _col("channel", "Canal", None, 10), _col("invoices_txt", "Factures", None, 24), _col("amount_due_tnd", "Montant dû", A),
                        _col("responsible", "Responsable", None, 16), _col("result_label", "Résultat", None, 16),
                        _col("next_action_date", "Prochaine action", "date", 12), _col("comments", "Commentaires", None, 30)],
            "rows": rows, "totals": None}


CATALOG = {
    "grand-livre": ("Grand livre auxiliaire clients", r_grand_livre),
    "balance-auxiliaire": ("Balance auxiliaire clients", r_balance_auxiliaire),
    "etat-creances": ("État détaillé des créances", r_etat_creances),
    "balance-agee": ("Balance âgée", r_balance_agee),
    "journal-ventes": ("Journal des ventes", r_journal_ventes),
    "journal-encaissements": ("Journal des encaissements", r_journal_encaissements),
    "factures-impayees": ("État des factures impayées", r_factures_impayees),
    "creances-douteuses": ("État des créances douteuses", r_creances_douteuses),
    "provisions": ("État des provisions", r_provisions),
    "depassements-plafond": ("État des dépassements de plafond", r_depassements),
    "prevision-encaissements": ("Prévision des encaissements", r_prevision),
    "historique-relances": ("Historique des relances", r_relances),
}


def build(db: Session, name: str, params: dict) -> dict:
    if name not in CATALOG:
        raise HTTPException(404, "État inconnu")
    return CATALOG[name][1](db, params)
